from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from os import path
from config import FROM, TO, SMTP_SERVER, SMTP_PORT, SMTP_PWD, SMTP_USER
import mimetypes
import smtplib
import zhihukindle
import sys

reload(sys)
sys.setdefaultencoding('utf8')


if __name__ == "__main__":
    from sys import argv, exit
    output_dir = "./output"
    if not len(argv) > 1:
        zhihukindle.main()
    print("-> Sending Email...")

    msg = MIMEMultipart()
    msg['From'] = FROM
    msg['To'] = ','.join(TO)
    msg['Subject'] = 'Zhihu Daily %s' % date.today().strftime("%Y%m%d")

    msg.attach(MIMEText(""))

    ctype, encoding = mimetypes.guess_type(path.join(output_dir, 'daily.mobi'))
    if ctype is None or encoding is not None:
        ctype = 'application/octet-stream'
    maintype, subtype = ctype.split('/', 1)

    fp = open(output_dir + '/daily.mobi', 'rb')
    part = MIMEBase(maintype, subtype)
    part.set_payload(fp.read())
    fp.close()
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment', filename="daily.mobi")
    msg.attach(part)

    smtp = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    smtp.login(SMTP_USER, SMTP_PWD)
    smtp.sendmail(FROM, TO,  msg.as_string())
    smtp.close()
