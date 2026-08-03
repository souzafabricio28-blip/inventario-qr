"""Helper para detectar IP da rede automaticamente."""
import socket


def obter_ip_rede():
    """
    Descobre o IP da interface de rede ativa.
    Técnica: cria socket UDP e lê o IP local da conexão.
    """
    # Lista de IPs externos para tentar
    test_endpoints = [
        ("8.8.8.8", 53),
        ("1.1.1.1", 53),
        ("8.8.4.4", 53),
        ("9.9.9.9", 53),
        ("208.67.222.222", 53),
    ]
    
    for host, port in test_endpoints:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect((host, port))
            local_ip = s.getsockname()[0]
            s.close()
            if local_ip and not local_ip.startswith("127."):
                return local_ip
        except Exception:
            continue
    
    # Fallback: tenta resolver hostname
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        pass
    
    return "127.0.0.1"