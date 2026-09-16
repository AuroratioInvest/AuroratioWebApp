import asyncio
from types import SimpleNamespace

from services import email_service


class FakeAsyncClient:
    response = SimpleNamespace(status_code=202, text="")
    last_request = None

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, *, json, headers):
        type(self).last_request = {
            "url": url,
            "json": json,
            "headers": headers,
            "timeout": self.timeout,
        }
        return type(self).response


def test_brevo_email_success(monkeypatch):
    FakeAsyncClient.response = SimpleNamespace(status_code=202, text="")
    FakeAsyncClient.last_request = None
    monkeypatch.setattr(email_service, "BREVO_API_KEY", "brevo-test-key")
    monkeypatch.setattr(email_service.httpx, "AsyncClient", FakeAsyncClient)

    sent = asyncio.run(
        email_service.send_email(
            to_email="subscriber@example.com",
            to_name="Subscriber",
            subject="Test subject",
            html_content="<p>Test body</p>",
        )
    )

    assert sent is True
    assert FakeAsyncClient.last_request["url"] == email_service.BREVO_API_URL
    assert FakeAsyncClient.last_request["headers"]["api-key"] == "brevo-test-key"
    assert FakeAsyncClient.last_request["json"]["to"] == [
        {"email": "subscriber@example.com", "name": "Subscriber"}
    ]


def test_brevo_email_http_failure(monkeypatch):
    FakeAsyncClient.response = SimpleNamespace(status_code=400, text="bad request")
    monkeypatch.setattr(email_service, "BREVO_API_KEY", "brevo-test-key")
    monkeypatch.setattr(email_service.httpx, "AsyncClient", FakeAsyncClient)

    sent = asyncio.run(
        email_service.send_email(
            to_email="subscriber@example.com",
            subject="Test subject",
            html_content="<p>Test body</p>",
        )
    )

    assert sent is False


def test_brevo_email_is_not_attempted_without_api_key(monkeypatch):
    monkeypatch.setattr(email_service, "BREVO_API_KEY", None)

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("HTTP client must not be created without a Brevo key")

    monkeypatch.setattr(email_service.httpx, "AsyncClient", UnexpectedClient)

    assert asyncio.run(
        email_service.send_email(
            to_email="subscriber@example.com",
            subject="Test subject",
            html_content="<p>Test body</p>",
        )
    ) is False


def test_billing_management_email_is_bilingual_and_escapes_link(monkeypatch):
    captured = []

    async def fake_send_email(**kwargs):
        captured.append(kwargs)
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send_email)

    assert asyncio.run(
        email_service.send_billing_management_link(
            to_email="subscriber@example.com",
            portal_link="https://app.example.test/manage#token=a&b",
            locale="en",
        )
    ) is True
    assert asyncio.run(
        email_service.send_billing_management_link(
            to_email="subscriber@example.com",
            portal_link="https://app.example.test/manage#token=c&d",
            locale="fr",
        )
    ) is True

    assert "secure AuroRatio billing-management link" in captured[0]["subject"]
    assert "une seule fois" in captured[1]["html_content"]
    assert "token=a&amp;b" in captured[0]["html_content"]
    assert "token=c&amp;d" in captured[1]["html_content"]


def test_billing_management_email_groups_distinct_customer_links_safely(
    monkeypatch,
):
    captured = {}

    async def fake_send_email(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send_email)

    sent = asyncio.run(
        email_service.send_billing_management_links(
            to_email="subscriber@example.com",
            locale="en",
            links=[
                {
                    "label": "Monthly signals — Active",
                    "url": "https://app.example.test/manage#token=one&safe",
                },
                {
                    "label": "Monthly signals — Historical <record>",
                    "url": "https://app.example.test/manage#token=two&safe",
                },
            ],
        )
    )

    assert sent is True
    assert "Monthly signals — Active" in captured["html_content"]
    assert "Historical &lt;record&gt;" in captured["html_content"]
    assert "token=one&amp;safe" in captured["html_content"]
    assert "token=two&amp;safe" in captured["html_content"]
    assert "cus_" not in captured["html_content"]
    assert "sub_" not in captured["html_content"]


def test_private_access_email_is_provider_neutral_and_escapes_invites(monkeypatch):
    captured = []

    async def fake_send_email(**kwargs):
        captured.append(kwargs)
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send_email)

    assert asyncio.run(
        email_service.send_private_access_instructions(
            to_email="subscriber@example.com",
            locale="en",
            invitations=[
                {
                    "label": "Monthly signals <private>",
                    "url": "https://t.me/+secret&value",
                }
            ],
        )
    ) is True
    assert asyncio.run(
        email_service.send_private_access_instructions(
            to_email="subscriber@example.com",
            locale="fr",
            invitations=[
                {
                    "label": "Signaux mensuels",
                    "url": "https://t.me/+secret-fr&value",
                }
            ],
        )
    ) is True

    assert "private access is ready" in captured[0]["html_content"]
    assert "personnelle" in captured[1]["html_content"]
    assert "t.me/+secret&amp;value" in captured[0]["html_content"]
    assert "Telegram" not in captured[0]["html_content"]
    assert "Telegram" not in captured[1]["html_content"]
    assert "cus_" not in captured[0]["html_content"]
    assert "sub_" not in captured[0]["html_content"]


def test_brevo_redirect_is_not_delivery_confirmation(monkeypatch):
    FakeAsyncClient.response = SimpleNamespace(status_code=302, text='')
    monkeypatch.setattr(email_service, 'BREVO_API_KEY', 'brevo-test-key')
    monkeypatch.setattr(email_service.httpx, 'AsyncClient', FakeAsyncClient)
    assert asyncio.run(email_service.send_email(
        to_email='subscriber@example.com', subject='Test', html_content='<p>Test</p>'
    )) is False
