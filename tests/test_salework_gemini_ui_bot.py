import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from salework_gemini_ui_bot import (
    extract_product_context,
    pick_variant,
    preview_skip_reason,
    quick_decision,
    safety_block_reason,
)


def test_quick_decision_missing_screws_is_safe():
    decision = quick_decision("shop ơi mình ko thấy gói ốc vít đâu", "")

    assert decision is not None
    assert decision.action == "send"
    assert "chụp" in decision.reply
    assert safety_block_reason(decision.reply) is None


def test_quick_decision_private_payment_redirects_to_shopee():
    decision = quick_decision("shop gửi số tài khoản đi", "")

    assert decision is not None
    assert decision.action == "send"
    assert "Shopee" in decision.reply
    assert safety_block_reason(decision.reply) is None


def test_safety_blocks_private_payment_terms():
    assert safety_block_reason("Dạ mình chuyển khoản cho em qua số tài khoản này ạ") is not None


def test_safety_blocks_support_commitments():
    reply = "Dạ về phí vận chuyển cho đơn này, bên em sẽ hỗ trợ mình ạ"

    assert safety_block_reason(reply) is not None


def test_safety_blocks_send_commitments():
    reply = "Dạ bên em sẽ cố gắng gửi đơn ốc sớm nhất cho mình ạ"

    assert safety_block_reason(reply) is not None


def test_extract_product_context_from_salework_order():
    text = """
Thông tin đơn hàng
ĐANG GIAO
Mã: 260520VG2CYWYE
Kệ sách góc tường nhiều tầng, kệ đa năng lắp ghép có HẬU FULL chất liệu gỗ MDF phù Melamine ND40
Giá : 297.500 ₫
"""

    product = extract_product_context(text)

    assert product.code == "ND40"
    assert "Kệ sách" in product.name


def test_dimension_rule_uses_visible_product_instead_of_asking_code():
    chat = """
Thông tin đơn hàng
Bàn gaming, bàn học dài, bàn chân trụ tròn phong cách hiện đại nội thất TAGO chính hãng
Giá : 299.000 ₫
"""

    decision = quick_decision("cao bao nhiêu ạ", chat)

    assert decision is not None
    assert decision.action == "send"
    assert "75cm" in decision.reply
    assert "mã" not in decision.reply.lower()


def test_safety_blocks_asking_for_product_code():
    reply = "Dạ mình gửi em mã sản phẩm cụ thể để em kiểm tra lại chính xác nhất ạ."

    assert safety_block_reason(reply) is not None


def test_preview_skip_blocks_compensation_demand():
    assert preview_skip_reason("shop phải bồi thường cho tôi") is not None
    assert preview_skip_reason("đền bù 200k cho tôi") is not None
    assert preview_skip_reason("yêu cầu shop hoàn tiền ngay") is not None


def test_preview_skip_blocks_threats_and_reviews():
    assert preview_skip_reason("tôi sẽ đánh giá 1 sao") is not None
    assert preview_skip_reason("tôi sẽ báo cáo shop") is not None
    assert preview_skip_reason("tố cáo shop ra công an") is not None


def test_preview_skip_blocks_custom_modifications():
    assert preview_skip_reason("shop đục lỗ giúp em với") is not None
    assert preview_skip_reason("khoan thêm cho em 2 lỗ") is not None


def test_preview_skip_allows_simple_questions():
    assert preview_skip_reason("shop ơi bao giờ giao hàng ạ") is None
    assert preview_skip_reason("cảm ơn shop nha") is None
    assert preview_skip_reason("cho em hỏi mặt bàn dày bao nhiêu") is None


def test_pick_variant_is_deterministic_for_same_seed():
    a = pick_variant("thanks", "customer_a|20260525")
    b = pick_variant("thanks", "customer_a|20260525")
    assert a == b


def test_pick_variant_returns_valid_phrasing():
    reply = pick_variant("greeting", "anyone")
    assert reply
    assert safety_block_reason(reply) is None


def test_quick_decision_uses_variant_for_thanks():
    decision = quick_decision("cảm ơn shop nha", "")
    assert decision is not None
    assert decision.action == "send"
    assert "cảm ơn" in decision.reply.lower()
    assert safety_block_reason(decision.reply) is None


def test_quick_decision_greeting_returns_send():
    decision = quick_decision("shop ơi", "")
    assert decision is not None
    assert decision.action == "send"
    assert safety_block_reason(decision.reply) is None


def test_all_reply_variants_pass_safety_filter():
    from salework_gemini_ui_bot import REPLY_VARIATIONS

    for category, variants in REPLY_VARIATIONS.items():
        for variant in variants:
            reason = safety_block_reason(variant)
            assert reason is None, f"variant for {category!r} blocked: {reason} | {variant!r}"
