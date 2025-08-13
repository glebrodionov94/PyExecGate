import paramiko
import logging
from typing import Optional, Dict, Any, Union
import socket
import json
from time import perf_counter
import shlex
import config

# Настройка логирования
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SSHError(Exception):
    """Базовое исключение для SSH ошибок"""
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message)
        self.details = details

def execute_command(
    host: str,
    command: str,
    username: Optional[str] = config.SSH_USER,
    password: Optional[str] = config.SSH_PASSWORD,
    port: int = 22,
    timeout: int = 10,
    key_filename: Optional[str] = None,
    policy: str = "warning",
    parse_json: bool = True,
    buffer_size: int = 65535
) -> Dict[str, Any]:
    
    # Валидация параметров
    errors = []
    if not host: errors.append("host")
    if not username: errors.append("username")
    if not command: errors.append("command")
    if errors:
        raise SSHError(f"Missing required parameters: {', '.join(errors)}")
    
    if policy not in ('auto', 'warning', 'strict'):
        raise SSHError("Invalid host policy. Valid options: auto, warning, strict")

    result = {
        'status': 'error',
        'exit_code': -1,
        'stdout': None,
        'stderr': '',
        'error': '',
        'execution_time': 0.0,
        'host': host
    }

    start_time = perf_counter()
    
    try:
        # Инициализация SSH клиента
        with paramiko.SSHClient() as ssh_client:
            # Настройка политики хоста
            host_policy = {
                'auto': paramiko.AutoAddPolicy(),
                'warning': paramiko.WarningPolicy(),
                'strict': paramiko.RejectPolicy()
            }[policy]
            ssh_client.set_missing_host_key_policy(host_policy)

            # Параметры подключения
            connect_args = {
                'hostname': host,
                'port': port,
                'username': username,
                'timeout': timeout,
                'banner_timeout': 30,
                'auth_timeout': timeout
            }
            
            if password:
                connect_args['password'] = password
            if key_filename:
                connect_args['key_filename'] = key_filename

            logger.info(f"Connecting to {host}:{port} as {username}")
            ssh_client.connect(**connect_args)
            
            # Выполнение команды
            logger.debug(f"Executing command: {command}")
            transport = ssh_client.get_transport()
            with transport.open_session() as channel: # type: ignore
                channel.settimeout(timeout)
                channel.exec_command(command)
                
                # Чтение вывода с буферизацией
                stdout = bytearray()
                stderr = bytearray()
                
                while not channel.exit_status_ready():
                    if channel.recv_ready():
                        stdout.extend(channel.recv(buffer_size))
                    if channel.recv_stderr_ready():
                        stderr.extend(channel.recv_stderr(buffer_size))
                
                # Дозапись оставшихся данных
                stdout.extend(channel.recv(buffer_size))
                stderr.extend(channel.recv_stderr(buffer_size))
                
                exit_code = channel.recv_exit_status()
                stdout_str = stdout.decode().strip()
                stderr_str = stderr.decode().strip()

                # Обработка вывода
                if parse_json and stdout_str:
                    try:
                        result['stdout'] = json.loads(stdout_str)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse stdout as JSON")
                        result['stdout'] = stdout_str
                else:
                    result['stdout'] = stdout_str if stdout_str else None

                result.update({
                    'status': 'success' if exit_code == 0 else 'error',
                    'exit_code': exit_code,
                    'stderr': stderr_str
                })

    except paramiko.AuthenticationException as e:
        error_msg = "Authentication failed"
        logger.error(f"{error_msg}: {e}")
        result['error'] = f"{error_msg}: Check credentials"
    except (paramiko.SSHException, socket.error) as e:
        error_msg = f"Connection error: {type(e).__name__}"
        logger.error(f"{error_msg}: {e}")
        result['error'] = f"{error_msg}: {e}"
    except Exception as e:
        error_msg = f"Unexpected error: {type(e).__name__}"
        logger.exception(error_msg)
        result['error'] = f"{error_msg}: {e}"
    finally:
        result['execution_time'] = round(perf_counter() - start_time, 2)

    return result