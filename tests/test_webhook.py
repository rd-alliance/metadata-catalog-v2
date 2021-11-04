import hashlib
import hmac

from werkzeug.test import EnvironBuilder


def test_webhook(client, app):
    ping = {
        "ref": "refs/tags/simple-tag",
        "repository": {
            "full_name": "rd-alliance/metadata-catalog-v2",
        },
        "pusher": {
            "name": "Codertocat",
        },
    }
    msg = EnvironBuilder.json_dumps(ping, sort_keys=True)
    hash = hmac.new(
        app.config['WEBHOOK_SECRET'].encode('utf-8'),
        msg=msg.encode('utf-8'),
        digestmod=hashlib.sha1)
    headers = {
        'X-Hub-Signature': 'sha1=' + hash.hexdigest(),
        'X-Github-Event': "push",
        'X-Github-Delivery': "",
        }

    response = client.post(
        '/postreceive', headers=headers, json=ping, follow_redirects=True)
    assert response.status_code == 204
