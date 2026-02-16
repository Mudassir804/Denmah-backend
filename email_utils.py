import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import settings

def send_email(to: str, subject: str, body: str):
    """
    Send a general email using SMTP (e.g. for order confirmations).
    """
    try:
        # Create message
        msg = MIMEMultipart()
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = to
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        # Connect to the SMTP server
        # Note: If your server uses SSL (Port 465), change this to smtplib.SMTP_SSL
        with smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT) as server:
            server.starttls()  # Enable encryption (TLS)
            server.login(settings.EMAIL_USERNAME, settings.EMAIL_PASSWORD)
            server.send_message(msg)

        return {"status": "success", "message": f"Email sent to {to}"}

    except Exception as e:
        print(f"Failed to send email: {e}")
        return {"status": "error", "message": str(e)}

def send_contact_form_email(customer_email: str, subject: str, message_body: str):
    """
    Sends an email FROM the website system TO the business owner (you).
    Sets the customer's email as 'Reply-To' so you can reply directly.
    """
    try:
        msg = MIMEMultipart()
        
        # 1. The email comes from your server settings (info@denmahcraft.com)
        # This prevents spam filters from blocking it because the sender matches the server.
        msg["From"] = settings.EMAIL_FROM 
        
        # 2. It is sent TO you (the business owner) so you can read it.
        msg["To"] = settings.EMAIL_FROM 
        
        # 3. 'Reply-To' lets you click "Reply" in your inbox and have it go to the customer.
        msg["Reply-To"] = customer_email
        
        msg["Subject"] = subject

        # The content you see in your inbox
        email_content = f"""
        You have received a new message from your website contact form.

        --------------------------------------------------
        From: {customer_email}
        Subject: {subject}
        --------------------------------------------------

        Message:
        {message_body}
        """

        msg.attach(MIMEText(email_content, "plain"))

        # Connect to the SMTP server
        with smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT) as server:
            server.starttls()
            server.login(settings.EMAIL_USERNAME, settings.EMAIL_PASSWORD)
            server.send_message(msg)

        return {"status": "success", "message": "Message sent successfully"}

    except Exception as e:
        print(f"Failed to send contact email: {e}")
        return {"status": "error", "message": str(e)}
