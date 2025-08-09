"""
Node Executor - Execute individual nodes with advanced error handling
"""
import asyncio
import importlib
import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

from django.conf import settings
from apps.nodes.models import NodeType, NodeCredential
from apps.core.exceptions import NodeExecutionError, NodeConfigurationError

logger = logging.getLogger(__name__)


@dataclass
class NodeExecutionResult:
    """Result of node execution"""
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    execution_time: float = 0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class NodeExecutor:
    """
    Advanced node executor with plugin system and security
    """

    def __init__(self):
        self.executor_cache = {}
        self.credential_cache = {}

    async def execute_node(
            self,
            node_type: NodeType,
            configuration: Dict[str, Any],
            input_data: Dict[str, Any],
            context: 'ExecutionContext'
    ) -> Dict[str, Any]:
        """
        Execute a node with comprehensive error handling and monitoring
        """
        start_time = time.time()

        try:
            # Validate configuration
            is_valid, validation_errors = node_type.validate_configuration(configuration)
            if not is_valid:
                raise NodeConfigurationError(f"Invalid configuration: {validation_errors}")

            # Get executor instance
            executor = await self._get_executor_instance(node_type)

            # Prepare execution environment
            execution_env = await self._prepare_execution_environment(
                node_type, configuration, context
            )

            # Execute node
            if hasattr(executor, 'execute_async'):
                result = await executor.execute_async(input_data, configuration, execution_env)
            else:
                # Run synchronous executor in thread pool
                result = await asyncio.get_event_loop().run_in_executor(
                    None, executor.execute, input_data, configuration, execution_env
                )

            execution_time = (time.time() - start_time) * 1000  # milliseconds

            # Validate output
            validated_result = await self._validate_output(result, node_type)

            # Increment node usage
            node_type.increment_usage()

            logger.debug(f"Node {node_type.name} executed successfully in {execution_time:.2f}ms")

            return validated_result

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Node {node_type.name} execution failed: {str(e)}")
            raise NodeExecutionError(f"Node execution failed: {str(e)}") from e

    async def _get_executor_instance(self, node_type: NodeType):
        """Get executor instance with caching"""
        cache_key = f"{node_type.name}_{node_type.version}"

        if cache_key in self.executor_cache:
            return self.executor_cache[cache_key]

        try:
            # Import executor class
            module_path, class_name = node_type.executor_class.rsplit('.', 1)
            module = importlib.import_module(module_path)
            executor_class = getattr(module, class_name)

            # Create instance
            executor = executor_class()

            # Cache for reuse
            self.executor_cache[cache_key] = executor

            return executor

        except (ImportError, AttributeError) as e:
            raise NodeExecutionError(f"Failed to load executor {node_type.executor_class}: {str(e)}")

    async def _prepare_execution_environment(
            self,
            node_type: NodeType,
            configuration: Dict[str, Any],
            context: 'ExecutionContext'
    ) -> Dict[str, Any]:
        """Prepare execution environment with credentials and context"""

        environment = {
            'context': context,
            'credentials': {},
            'settings': configuration.get('settings', {}),
            'organization_id': context.organization_id,
            'user_id': context.user_id,
        }

        # Load required credentials
        required_credentials = node_type.required_credentials
        for cred_type in required_credentials:
            credential_name = configuration.get(f'{cred_type}_credential')
            if credential_name:
                credential = await self._get_credential(credential_name, context.organization_id)
                if credential:
                    environment['credentials'][cred_type] = credential.get_decrypted_data()

        return environment

    async def _get_credential(self, credential_name: str, organization_id: str) -> Optional[NodeCredential]:
        """Get credential with caching"""
        cache_key = f"{organization_id}_{credential_name}"

        if cache_key in self.credential_cache:
            return self.credential_cache[cache_key]

        try:
            credential = await NodeCredential.objects.aget(
                name=credential_name,
                organization_id=organization_id,
                is_active=True
            )

            # Check if credential is expired
            if credential.is_expired:
                logger.warning(f"Credential {credential_name} is expired")
                return None

            # Cache for reuse (with TTL in production)
            self.credential_cache[cache_key] = credential

            # Update last used
            credential.last_used_at = time.now()
            await credential.asave(update_fields=['last_used_at'])

            return credential

        except NodeCredential.DoesNotExist:
            logger.warning(f"Credential {credential_name} not found")
            return None

    async def _validate_output(self, result: Any, node_type: NodeType) -> Dict[str, Any]:
        """Validate node output against schema"""

        if not isinstance(result, dict):
            # Convert single values to main output
            result = {'main': result}

        # Validate against output schema
        output_schema = node_type.outputs_schema
        validated_output = {}

        for output_def in output_schema:
            output_name = output_def['name']
            output_type = output_def.get('type', 'any')
            required = output_def.get('required', False)

            if output_name in result:
                value = result[output_name]

                # Type validation
                if output_type != 'any':
                    validated_value = await self._validate_output_type(value, output_type)
                    validated_output[output_name] = validated_value
                else:
                    validated_output[output_name] = value
            elif required:
                raise NodeExecutionError(f"Required output '{output_name}' not provided")

        # Include any additional outputs not in schema
        for key, value in result.items():
            if key not in validated_output:
                validated_output[key] = value

        return validated_output

    async def _validate_output_type(self, value: Any, expected_type: str) -> Any:
        """Validate and convert output type"""

        type_validators = {
            'string': lambda x: str(x),
            'number': lambda x: float(x) if isinstance(x, (int, float, str)) else x,
            'integer': lambda x: int(x) if isinstance(x, (int, float, str)) else x,
            'boolean': lambda x: bool(x),
            'array': lambda x: list(x) if not isinstance(x, list) else x,
            'object': lambda x: dict(x) if isinstance(x, dict) else x,
        }

        validator = type_validators.get(expected_type)
        if validator:
            try:
                return validator(value)
            except (ValueError, TypeError) as e:
                logger.warning(f"Type conversion failed for {expected_type}: {str(e)}")

        return value


# Base classes for node executors
class BaseNodeExecutor:
    """Base class for all node executors"""

    def validate_configuration(self, configuration: Dict[str, Any]) -> tuple[bool, list]:
        """Validate node configuration"""
        return True, []

    def execute(self, input_data: Dict[str, Any], configuration: Dict[str, Any], environment: Dict[str, Any]) -> Dict[
        str, Any]:
        """Execute node (synchronous)"""
        raise NotImplementedError("Subclasses must implement execute method")

    async def execute_async(self, input_data: Dict[str, Any], configuration: Dict[str, Any],
                            environment: Dict[str, Any]) -> Dict[str, Any]:
        """Execute node (asynchronous) - override for async nodes"""
        return self.execute(input_data, configuration, environment)

    def get_credential(self, environment: Dict[str, Any], credential_type: str) -> Dict[str, Any]:
        """Get credential from environment"""
        return environment.get('credentials', {}).get(credential_type, {})

    def log_info(self, message: str):
        """Log info message"""
        logger.info(f"[{self.__class__.__name__}] {message}")

    def log_error(self, message: str):
        """Log error message"""
        logger.error(f"[{self.__class__.__name__}] {message}")


class HTTPNodeExecutor(BaseNodeExecutor):
    """Base class for HTTP-based node executors"""

    async def execute_async(self, input_data: Dict[str, Any], configuration: Dict[str, Any],
                            environment: Dict[str, Any]) -> Dict[str, Any]:
        import aiohttp
        import json as json_lib

        method = configuration.get('method', 'GET').upper()
        url = configuration.get('url', '')
        headers = configuration.get('headers', {})

        # Merge input data if specified
        if configuration.get('mergeInputData', False):
            if method in ['POST', 'PUT', 'PATCH']:
                json_data = input_data
            else:
                params = input_data
        else:
            json_data = configuration.get('body', {})
            params = configuration.get('params', {})

        # Add authentication
        auth_type = configuration.get('authentication', {}).get('type')
        if auth_type == 'bearer':
            token = configuration.get('authentication', {}).get('token')
            headers['Authorization'] = f'Bearer {token}'
        elif auth_type == 'api_key':
            api_key = self.get_credential(environment, 'api_key').get('key', '')
            key_location = configuration.get('authentication', {}).get('location', 'header')
            key_name = configuration.get('authentication', {}).get('name', 'X-API-Key')

            if key_location == 'header':
                headers[key_name] = api_key
            elif key_location == 'query':
                params[key_name] = api_key

        try:
            timeout = aiohttp.ClientTimeout(total=configuration.get('timeout', 30))

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params if method == 'GET' else None,
                        json=json_data if method in ['POST', 'PUT', 'PATCH'] else None
                ) as response:

                    # Get response data
                    content_type = response.headers.get('content-type', '')

                    if 'application/json' in content_type:
                        response_data = await response.json()
                    else:
                        response_data = await response.text()

                    result = {
                        'statusCode': response.status,
                        'headers': dict(response.headers),
                        'body': response_data
                    }

                    # Check for HTTP errors
                    if response.status >= 400:
                        error_message = f"HTTP {response.status}: {response_data}"
                        if configuration.get('continueOnFail', False):
                            result['error'] = error_message
                        else:
                            raise NodeExecutionError(error_message)

                    return result

        except aiohttp.ClientError as e:
            raise NodeExecutionError(f"HTTP request failed: {str(e)}")
        except asyncio.TimeoutError:
            raise NodeExecutionError("HTTP request timed out")


class DatabaseNodeExecutor(BaseNodeExecutor):
    """Base class for database node executors"""

    def get_connection_string(self, environment: Dict[str, Any]) -> str:
        """Get database connection string from credentials"""
        db_creds = self.get_credential(environment, 'database')

        host = db_creds.get('host', 'localhost')
        port = db_creds.get('port', 5432)
        database = db_creds.get('database', '')
        username = db_creds.get('username', '')
        password = db_creds.get('password', '')

        return f"postgresql://{username}:{password}@{host}:{port}/{database}"

    async def execute_query(self, query: str, params: list, environment: Dict[str, Any]) -> Dict[str, Any]:
        """Execute database query"""
        import asyncpg

        connection_string = self.get_connection_string(environment)

        try:
            conn = await asyncpg.connect(connection_string)

            try:
                if query.strip().upper().startswith('SELECT'):
                    # Select query
                    rows = await conn.fetch(query, *params)
                    result = [dict(row) for row in rows]
                    return {'rows': result, 'rowCount': len(result)}
                else:
                    # Insert/Update/Delete query
                    result = await conn.execute(query, *params)
                    return {'message': result,
                            'rowCount': int(result.split()[-1]) if result.split()[-1].isdigit() else 0}

            finally:
                await conn.close()

        except Exception as e:
            raise NodeExecutionError(f"Database query failed: {str(e)}")


class EmailNodeExecutor(BaseNodeExecutor):
    """Base class for email node executors"""

    async def send_email(
            self,
            to_addresses: list,
            subject: str,
            body: str,
            environment: Dict[str, Any],
            is_html: bool = False
    ) -> Dict[str, Any]:
        """Send email using configured provider"""

        # Get email credentials
        email_creds = self.get_credential(environment, 'email')
        provider = email_creds.get('provider', 'smtp')

        if provider == 'sendgrid':
            return await self._send_via_sendgrid(to_addresses, subject, body, email_creds, is_html)
        else:
            return await self._send_via_smtp(to_addresses, subject, body, email_creds, is_html)

    async def _send_via_sendgrid(self, to_addresses, subject, body, credentials, is_html):
        """Send email via SendGrid"""
        import sendgrid
        from sendgrid.helpers.mail import Mail

        sg = sendgrid.SendGridAPIClient(api_key=credentials.get('api_key'))

        message = Mail(
            from_email=credentials.get('from_email'),
            to_emails=to_addresses,
            subject=subject,
            html_content=body if is_html else None,
            plain_text_content=body if not is_html else None
        )

        try:
            response = sg.send(message)
            return {
                'success': True,
                'message_id': response.headers.get('X-Message-Id'),
                'status_code': response.status_code
            }
        except Exception as e:
            raise NodeExecutionError(f"SendGrid email failed: {str(e)}")

    async def _send_via_smtp(self, to_addresses, subject, body, credentials, is_html):
        """Send email via SMTP"""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = credentials.get('from_email')
            msg['To'] = ', '.join(to_addresses)

            # Add body
            if is_html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))

            # Send email
            with smtplib.SMTP(credentials.get('smtp_host'), credentials.get('smtp_port', 587)) as server:
                server.starttls()
                server.login(credentials.get('username'), credentials.get('password'))
                server.send_message(msg)

            return {
                'success': True,
                'recipients': to_addresses,
                'message': 'Email sent successfully'
            }

        except Exception as e:
            raise NodeExecutionError(f"SMTP email failed: {str(e)}")


# Global node executor instance
node_executor = NodeExecutor()