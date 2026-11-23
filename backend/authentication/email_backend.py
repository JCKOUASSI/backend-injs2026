import ssl
import smtplib
from django.core.mail.backends.smtp import EmailBackend


class UnverifiedSSLEmailBackend(EmailBackend):
    """
    Backend SMTP identique au backend Django standard, mais avec la
    vérification du certificat SSL désactivée.
    Utile pour les serveurs auto-hébergés (ex: Mailcow) avec un
    certificat auto-signé.
    """

    def _get_ssl_context(self):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    def open(self):
        if self.connection:
            return False

        connection_params = {"host": self.host, "port": self.port}
        if self.timeout is not None:
            connection_params["timeout"] = self.timeout

        try:
            if self.use_ssl:
                connection_params["context"] = self._get_ssl_context()
                self.connection = smtplib.SMTP_SSL(**connection_params)
            else:
                self.connection = smtplib.SMTP(**connection_params)

            if self.use_tls:
                self.connection.ehlo()
                self.connection.starttls(context=self._get_ssl_context())
                self.connection.ehlo()

            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except Exception:
            if not self.fail_silently:
                raise
