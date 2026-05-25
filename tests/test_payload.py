from app.payload import parse_salework_payload


def test_parse_nested_payload_with_image_attachment():
    payload = {
        "data": {
            "conversation": {"id": "conv-1"},
            "sender": {"id": "buyer-1", "type": "buyer"},
            "message": {
                "id": "msg-1",
                "content": "Shop oi san pham nay con khong?",
                "attachments": [
                    {"type": "image", "url": "https://cdn.example.com/file/no-extension"},
                ],
            },
        }
    }

    event = parse_salework_payload(payload)

    assert event.conversation_id == "conv-1"
    assert event.customer_id == "buyer-1"
    assert event.message_id == "msg-1"
    assert event.text == "Shop oi san pham nay con khong?"
    assert event.image_urls == ["https://cdn.example.com/file/no-extension"]
    assert event.is_from_customer is True


def test_parse_shop_message_as_not_customer():
    payload = {
        "conversation_id": "conv-1",
        "sender_type": "shop",
        "message": "Cam on anh chi",
    }

    event = parse_salework_payload(payload)

    assert event.is_from_customer is False


def test_parse_history_messages():
    payload = {
        "conversation_id": "conv-1",
        "customer_id": "buyer-1",
        "message": {"id": "msg-2", "text": "Gia sao shop?"},
        "history": [
            {"role": "buyer", "text": "Xin chao"},
            {"role": "shop", "text": "Shop chao anh chi"},
        ],
    }

    event = parse_salework_payload(payload)

    assert event.text == "Gia sao shop?"
    assert event.history == [
        {"role": "buyer", "text": "Xin chao"},
        {"role": "shop", "text": "Shop chao anh chi"},
    ]


def test_parse_salework_columns_payload():
    payload = {
        "company_code": "sw80214c51176",
        "columns": [
            {"columnCode": "conversation_id", "value": "conv-from-columns"},
            {"columnCode": "channel", "value": "Shopee"},
            {"columnCode": "name", "value": "Nguyen A"},
            {"columnCode": "last_message", "value": "Shop oi tu nay go gi?"},
        ],
    }

    event = parse_salework_payload(payload)

    assert event.conversation_id == "conv-from-columns"
    assert event.text == "Shop oi tu nay go gi?"
