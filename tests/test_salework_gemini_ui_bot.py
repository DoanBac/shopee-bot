import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from salework_gemini_ui_bot import (
    PRODUCT_VIDEO_URLS,
    answer_from_product_description,
    attachment_related_reason,
    extract_dimension_answer,
    extract_product_context,
    is_product_info_request,
    is_send_reference_request,
    is_short_followup_request,
    pick_variant,
    product_note,
    preview_skip_reason,
    quick_decision,
    safety_block_reason,
    shorten_reply,
)


def test_quick_decision_missing_screws_is_human_only():
    decision = quick_decision("shop ơi mình ko thấy gói ốc vít đâu", "")

    assert decision is not None
    assert decision.action == "skip"
    assert decision.category == "screw_related"


def test_quick_decision_accessory_or_screw_history_is_human_only():
    decision = quick_decision("shop ơi phụ kiện đâu ạ", "")

    assert decision is not None
    assert decision.action == "skip"
    assert decision.category == "screw_related"

    history_decision = quick_decision("shop hướng dẫn lắp giúp mình", "khách báo thiếu phụ kiện trong lịch sử chat")

    assert history_decision is not None
    assert history_decision.action == "skip"
    assert history_decision.category == "screw_related"


def test_quick_decision_missing_parts_is_human_only():
    for message in [
        "shop ơi em bị thiếu tấm ngăn",
        "đơn này giao thiếu chi tiết rồi",
        "mình không thấy cái chân bàn đâu",
    ]:
        decision = quick_decision(message, "")

        assert decision is not None
        assert decision.action == "skip"
        assert decision.category == "missing_item"


def test_quick_decision_private_payment_is_human_only():
    decision = quick_decision("shop gửi số tài khoản đi", "")

    assert decision is not None
    assert decision.action == "skip"
    assert decision.category == "private_payment"


def test_quick_decision_return_refund_is_human_only():
    for message in [
        "shop ơi em muốn trả hàng hoàn tiền",
        "mình muốn hoàn hàng",
        "shop xử lý đổi trả giúp mình",
    ]:
        decision = quick_decision(message, "")

        assert decision is not None
        assert decision.action == "skip"
        assert decision.category == "return_refund"


def test_angry_defect_context_never_sends_video_from_shop_auto_message():
    chat = """
Tại sao e mua 1 màu shop giao màu khác?
E ở SG shop ở HN lận á, đã mua xa xôi, khui ra lại k đúng màu sp
Alo shop, giờ e đổi trả hay sao shop
Lần đầu mua thất vọng dã man
Nếu quý khách cần xem video hướng dẫn sản phẩm, xin mời truy cập YouTube
www.youtube.com/@TagoFurniture2412
Quá mất công đổi nên đã lắp luôn. Độ hoàn thiện thấp, chân tủ yếu.
Quá mệt
Uổng tiền
Cửa bị sứt 1 miếng nữa chứ
"""

    decision = quick_decision("Quá mệt", chat)

    assert decision is not None
    assert decision.action == "skip"
    assert decision.category == "complaint_defect"

    followup = quick_decision("gấp giúp em ạ", chat)

    assert followup is not None
    assert followup.action == "skip"
    assert followup.category == "complaint_defect"

    assert preview_skip_reason("Cửa bị sứt 1 miếng nữa chứ") == "complaint/defect case: human only"
    assert preview_skip_reason("Tại sao e mua 1 màu shop giao màu khác?") == "complaint/defect case: human only"


def test_safety_blocks_private_payment_terms():
    assert safety_block_reason("Dạ mình chuyển khoản cho em qua số tài khoản này ạ") is not None


def test_safety_blocks_support_commitments():
    reply = "Dạ về phí vận chuyển cho đơn này, bên em sẽ hỗ trợ mình ạ"

    assert safety_block_reason(reply) is not None


def test_safety_blocks_send_commitments():
    reply = "Dạ bên em sẽ cố gắng gửi đơn ốc sớm nhất cho mình ạ"

    assert safety_block_reason(reply) is not None


def test_safety_blocks_any_screw_or_accessory_terms():
    assert safety_block_reason("Dạ bên em có gửi kèm ốc vít rồi ạ") is not None
    assert safety_block_reason("Dạ mình chuẩn bị tua vít giúp em nha") is not None
    assert safety_block_reason("Dạ phần phụ kiện em kiểm tra lại cho mình ạ") is not None


def test_safety_blocks_missing_parts_terms():
    assert safety_block_reason("Dạ phần thiếu tấm ngăn em kiểm tra lại cho mình ạ") is not None
    assert safety_block_reason("Dạ đơn này giao thiếu chi tiết nên em ghi nhận ạ") is not None


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


def test_safety_blocks_sending_customer_to_description_or_live():
    assert safety_block_reason("Dạ mình xem phần mô tả sản phẩm giúp em nha") is not None
    assert safety_block_reason("Dạ mình tham khảo mô tả sản phẩm trên Shopee giúp em ạ") is not None
    assert safety_block_reason("Dạ mình xem live của shop để các bạn đo trực tiếp giúp em nha") is not None


def test_safety_blocks_generic_youtube_channel_link():
    assert (
        safety_block_reason(
            "Dạ mình xem video hướng dẫn của shop ở đây giúp em nha: https://www.youtube.com/@TagoFurniture2412"
        )
        is not None
    )
    assert (
        safety_block_reason(
            "Dạ mẫu này mã ND40, mình xem video hướng dẫn lắp đúng mẫu ở đây giúp em nha: https://www.youtube.com/watch?v=WgSEC9Wccno"
        )
        is None
    )


def test_safety_blocks_return_refund_terms():
    assert safety_block_reason("Dạ mình vào Shopee bấm trả hàng hoàn tiền giúp em ạ") is not None
    assert safety_block_reason("Dạ Shopee sẽ xử lý hoàn tiền cho mình ạ") is not None
    assert safety_block_reason("Dạ trường hợp đổi trả này em hỗ trợ mình kiểm tra ạ") is not None


def test_product_note_tells_gemini_to_use_visible_product_not_customer_lookup():
    chat = """
Thông tin đơn hàng
Bàn gaming, bàn học dài, bàn chân trụ tròn phong cách hiện đại nội thất TAGO chính hãng ND01
Giá : 299.000 ₫
"""

    note = product_note(chat)

    assert "ND01" in note
    assert "Tu dung thong tin san pham" in note
    assert "khong bao khach tu xem mo ta" in note


def test_preview_skip_blocks_compensation_demand():
    assert preview_skip_reason("shop phải bồi thường cho tôi") is not None
    assert preview_skip_reason("đền bù 200k cho tôi") is not None
    assert preview_skip_reason("yêu cầu shop hoàn tiền ngay") is not None


def test_preview_skip_blocks_cost_fee_without_click():
    assert preview_skip_reason("phí hư tính sao shop") == "cost/fee case: human only"
    assert preview_skip_reason("shop hỗ trợ chi phí không") == "cost/fee case: human only"
    assert preview_skip_reason("giá bao nhiêu vậy") == "cost/fee case: human only"


def test_preview_skip_blocks_image_or_attachment_without_click():
    assert preview_skip_reason("[Hình ảnh]") == "image/attachment case: human only"
    assert attachment_related_reason("khách vừa gửi [Hình ảnh]") == "image/attachment case: human only"


def test_preview_skip_blocks_return_refund_cases_without_click():
    assert preview_skip_reason("shop ơi mình muốn trả hàng hoàn tiền") == "return/refund case: human only"
    assert preview_skip_reason("hàng lỗi mình muốn hoàn hàng") == "return/refund case: human only"
    assert preview_skip_reason("tôi cần đổi trả đơn này") == "return/refund case: human only"


def test_preview_skip_blocks_threats_and_reviews():
    assert preview_skip_reason("tôi sẽ đánh giá 1 sao") is not None
    assert preview_skip_reason("tôi sẽ báo cáo shop") is not None
    assert preview_skip_reason("tố cáo shop ra công an") is not None


def test_preview_skip_blocks_custom_modifications():
    assert preview_skip_reason("shop đục lỗ giúp em với") is not None
    assert preview_skip_reason("khoan thêm cho em 2 lỗ") is not None


def test_preview_skip_blocks_screw_cases_without_click():
    assert preview_skip_reason("shop ơi mình không thấy gói ốc vít đâu") == "screw-related case: human only"
    assert preview_skip_reason("cần tua vít gì để lắp") == "screw-related case: human only"
    assert preview_skip_reason("shop ơi thiếu phụ kiện rồi") == "screw-related case: human only"


def test_preview_skip_blocks_missing_parts_without_click():
    assert preview_skip_reason("shop ơi thiếu tấm ngăn rồi") == "missing item/part case: human only"
    assert preview_skip_reason("đơn này giao thiếu chi tiết") == "missing item/part case: human only"
    assert preview_skip_reason("mình không thấy cái cánh tủ") == "missing item/part case: human only"


def test_preview_skip_allows_simple_questions():
    assert preview_skip_reason("shop ơi bao giờ giao hàng ạ") == "outside product-info scope"
    assert preview_skip_reason("cảm ơn shop nha") == "outside product-info scope"
    assert preview_skip_reason("cho em hỏi mặt bàn dày bao nhiêu") is None


def test_pick_variant_is_deterministic_for_same_seed():
    a = pick_variant("thanks", "customer_a|20260525")
    b = pick_variant("thanks", "customer_a|20260525")
    assert a == b


def test_pick_variant_returns_valid_phrasing():
    reply = pick_variant("greeting", "anyone")
    assert reply
    assert safety_block_reason(reply) is None


def test_quick_decision_thanks_is_outside_product_scope():
    decision = quick_decision("cảm ơn shop nha", "")
    assert decision is not None
    assert decision.action == "skip"
    assert decision.category == "outside_product_info_scope"


def test_quick_decision_greeting_is_outside_product_scope():
    decision = quick_decision("shop ơi", "")
    assert decision is not None
    assert decision.action == "skip"
    assert decision.category == "outside_product_info_scope"


def test_product_info_scope_detection():
    assert is_product_info_request("xin video lắp mẫu này")
    assert is_product_info_request("kích thước bao nhiêu")
    assert is_product_info_request("chất liệu gỗ gì")
    assert not is_product_info_request("bao giờ giao hàng")


def test_video_request_detection_common_customer_phrases():
    for message in [
        "K có dạy lắp à shop",
        "Cho e xem cách lắp",
        "Hướng dẫn anh cách lắp tủ nhé",
        "cách ráp kệ này sao shop",
        "B gửi mình hướng dẫn lắp nhé",
        "Shop có video hướng dẫn lắp kệ không",
        "có hdsd để lắp không ạ shop ơiiii",
        "cho mình xin link lắp kệ",
    ]:
        decision = quick_decision(message, "Thông tin đơn hàng\nKệ sách tổ ong ND38")

        assert decision is not None
        assert decision.action == "send"
        assert decision.category == "assembly_video"
        assert "https://www.youtube.com/watch?v=O2sUXRiuM5U" in decision.reply
        assert "@TagoFurniture2412" not in decision.reply


def test_nd90_video_request_uses_direct_product_video():
    decision = quick_decision(
        "shop gửi mình video hướng dẫn lắp với",
        "Thông tin đơn hàng\nTủ giày lắp ghép nội thất TAGO ND90\nGiá : 299.000đ",
    )

    assert decision is not None
    assert decision.action == "send"
    assert decision.category == "assembly_video"
    assert "https://www.youtube.com/watch?v=HCU50Y-7tIg" in decision.reply
    assert "@TagoFurniture2412" not in decision.reply


def test_nd40_video_request_uses_direct_product_video():
    decision = quick_decision(
        "shop cho em xin video hướng dẫn lắp",
        "Thông tin đơn hàng\nKệ sách góc tường nhiều tầng có hậu TAGO ND40\nGiá : 258.000đ",
    )

    assert decision is not None
    assert decision.action == "send"
    assert decision.category == "assembly_video"
    assert "https://www.youtube.com/watch?v=WgSEC9Wccno" in decision.reply
    assert "@TagoFurniture2412" not in decision.reply


def test_all_product_video_urls_are_direct_watch_links():
    assert PRODUCT_VIDEO_URLS
    for code, url in PRODUCT_VIDEO_URLS.items():
        assert code.startswith("ND")
        assert url.startswith("https://www.youtube.com/watch?v=")
        assert "/@" not in url
        assert "playlist" not in url


def test_nd90_self_assembly_uses_direct_product_video():
    decision = quick_decision(
        "mẫu này có tự lắp không",
        "Thông tin đơn hàng\nTủ giày lắp ghép nội thất TAGO ND90\nGiá : 299.000đ",
    )

    assert decision is not None
    assert decision.action == "send"
    assert decision.category == "self_assembly"
    assert "https://www.youtube.com/watch?v=HCU50Y-7tIg" in decision.reply


def test_unknown_product_video_request_is_human_only():
    decision = quick_decision(
        "shop gửi mình video hướng dẫn lắp với",
        "Thông tin đơn hàng\nKệ mới chưa có video TAGO ND999\nGiá : 299.000đ",
    )

    assert decision is not None
    assert decision.action == "skip"
    assert decision.category == "assembly_video_missing"


def test_video_request_without_product_code_is_human_only():
    decision = quick_decision("shop gửi mình video hướng dẫn lắp với", "Thông tin đơn hàng\nKệ sách")

    assert decision is not None
    assert decision.action == "skip"
    assert decision.category == "assembly_video_missing"


def test_send_reference_preview_opens_only_for_recent_video_context():
    assert is_send_reference_request("Shop gửi qua đây giúp mình với")
    assert preview_skip_reason("Shop gửi qua đây giúp mình với") is None
    assert preview_skip_reason("Gửi gấp cho chị với") == "outside product-info scope"

    decision = quick_decision(
        "Shop gửi qua đây giúp mình với",
        "khách vừa nhắn: em xin video hướng dẫn lắp kệ với ạ\nThông tin đơn hàng\nKệ sách ND38",
    )

    assert decision is not None
    assert decision.action == "send"
    assert decision.category == "assembly_video"

    no_context = quick_decision("Shop gửi qua đây giúp mình với", "khách hỏi bao giờ giao hàng")

    assert no_context is not None
    assert no_context.action == "skip"
    assert no_context.category == "ambiguous_send_reference"


def test_short_followup_after_hdsd_context_sends_video():
    assert is_short_followup_request("gấp giúp em ạ")
    assert preview_skip_reason("gấp giúp em ạ") is None

    decision = quick_decision(
        "gấp giúp em ạ",
        "khách: có hdsd để lắp không ạ shop ơiiii\nThông tin đơn hàng\nTủ giày ND40",
    )

    assert decision is not None
    assert decision.action == "send"
    assert decision.category == "assembly_video"

    no_context = quick_decision("gấp giúp em ạ", "khách hỏi giao hàng nhanh được không")

    assert no_context is not None
    assert no_context.action == "skip"
    assert no_context.category == "ambiguous_short_followup"


def test_extract_dimension_answer_from_description():
    answer = extract_dimension_answer("Mô tả\nKích thước: 120 x 60 x 75cm\nChất liệu MDF", "kích thước")
    assert answer is not None
    assert "120 x 60 x 75cm" in answer

    height = extract_dimension_answer("Thông số\nChiều cao: 75cm", "cao bao nhiêu")
    assert height is not None
    assert "75cm" in height

    assert extract_dimension_answer("Giá: 299.000đ", "kích thước") is None


def test_product_lookup_ignores_search_result_noise_for_shelf_comparison():
    text = "Search result for 'ND40 Ke sach goc tuong nhieu tang, ke da nang lap ghep co HAU FULL chat lieu go MDF phu Melamine ND40'"
    question = "chieu dai cac ngan cua ke 5 tang nay ngan hon chieu dai cac ngan cua ke 4 tang phai ko"

    assert answer_from_product_description(text, question) is None


def test_product_lookup_does_not_answer_comparative_dimension_from_single_size():
    text = "Mo ta san pham\nKich thuoc: 60 x 30 x 120cm\nChat lieu MDF"
    question = "chieu dai cac ngan cua ke 5 tang ngan hon ke 4 tang phai khong"

    assert answer_from_product_description(text, question) is None


def test_shorten_reply_caps_length():
    long_reply = "Dạ " + "nội dung " * 80
    reply = shorten_reply(long_reply, 120)
    assert len(reply) <= 120 + 3
    assert "\n" not in reply


def test_all_reply_variants_pass_safety_filter():
    from salework_gemini_ui_bot import REPLY_VARIATIONS

    for category, variants in REPLY_VARIATIONS.items():
        for variant in variants:
            reason = safety_block_reason(variant)
            assert reason is None, f"variant for {category!r} blocked: {reason} | {variant!r}"
