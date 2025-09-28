from dotenv import load_dotenv
import os, smtplib, traceback
from pathlib import Path

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).resolve().parents[0] / '..' / '.env')
server = os.getenv('SMTP_SERVER')
port = int(os.getenv('SMTP_PORT', '587'))
user = os.getenv('SMTP_USER')
pw = os.getenv('SMTP_PASSWORD')
use_tls = os.getenv('SMTP_USE_TLS', 'true').lower() in ('1','true','yes')

print('SMTP server=', server, 'port=', port, 'user=', user, 'use_tls=', use_tls)

try:
    s = smtplib.SMTP(server, port, timeout=20)
    print('CONNECTED')
    if use_tls:
        s.starttls()
        print('STARTTLS OK')
    s.login(user, pw)
    print('LOGIN OK')
    s.quit()
except Exception as e:
    traceback.print_exc()
    print('LOGIN FAILED:', e)
