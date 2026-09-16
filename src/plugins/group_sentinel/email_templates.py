"""群哨兵的待人工复核通知文案，不包含 SMTP 发送逻辑。"""

from html import escape


def _html_text(value: object) -> str:
    """动态内容只作为文字输出，保留换行，不把申请信息当作 HTML 执行。"""
    return escape(str(value)).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def build_pending_review_email(
    *, group_id: int, reason: str, contact: str, include_html: bool = False
) -> tuple[str, str | None]:
    """始终提供纯文本；HTML 使用表格和内联样式，不依赖外部图片、字体或脚本。"""
    paragraphs = [
        "您好，您的入群申请暂未通过自动初审，目前已挂起，等待管理员人工复核。",
        f"申请的 QQ 群：{group_id}",
        f"初审标记原因：{reason}",
        "这不是最终拒绝结果，您目前无需重复提交申请，请耐心等待人工复核。",
        "如发现填写的学号前 6 位有误，可联系管理员补充或更正信息。",
    ]
    if contact.strip():
        paragraphs.append(f"如需人工复核，可联系：{contact.strip()}")
    paragraphs.append("本邮件由机器人自动发送，请勿直接回复。")
    text = "\n\n".join(paragraphs)
    if not include_html:
        return text, None

    contact_block = ""
    if contact.strip():
        contact_block = f"""
          <tr>
            <td style="padding:0 24px 28px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                     bgcolor="#f5f3ff" style="width:100%;background-color:#f5f3ff;border-radius:10px;">
                <tr><td style="padding:18px 20px;word-break:break-all;overflow-wrap:anywhere;">
                  <p style="margin:0 0 6px;font-size:14px;line-height:22px;font-weight:700;color:#4338a0;">需要补充信息？</p>
                  <p style="margin:0 0 4px;font-size:14px;line-height:24px;color:#4b4563;">如需人工复核，可联系：</p>
                  <p style="margin:0;font-size:15px;line-height:26px;font-weight:600;color:#4338a0;word-break:normal;overflow-wrap:anywhere;">{_html_text(contact.strip())}</p>
                </td></tr>
              </table>
            </td>
          </tr>"""

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>入群申请待人工复核</title>
</head>
<body style="margin:0;padding:0;width:100%;background-color:#f3f4f8;color:#24263a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',Arial,sans-serif;-webkit-text-size-adjust:100%;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;font-size:1px;line-height:1px;mso-hide:all;">您的申请正在等待人工复核，无需重复提交。</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#f3f4f8"
         style="width:100%;background-color:#f3f4f8;">
    <tr><td align="center" style="padding:28px 12px;">
      <!--[if mso]><table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0"><tr><td><![endif]-->
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
             style="width:100%;max-width:600px;table-layout:fixed;">
        <tr><td style="padding:0 4px 14px;font-size:13px;line-height:20px;font-weight:700;letter-spacing:1px;color:#64677d;">谛听机器人 · 群哨兵</td></tr>
        <tr><td>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#ffffff"
                 style="width:100%;table-layout:fixed;background-color:#ffffff;border:1px solid #e4e6ef;border-top:4px solid #6d5be3;border-radius:14px;">
            <tr><td style="padding:28px 24px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                     style="width:100%;table-layout:fixed;margin:0 0 12px;">
                <tr>
                  <td valign="middle" style="padding:0 12px 0 0;">
                    <h1 style="margin:0;font-size:24px;line-height:34px;font-weight:700;letter-spacing:-0.5px;color:#25253d;">入群申请待<span style="white-space:nowrap;">人工复核</span></h1>
                  </td>
                  <td width="100" align="right" valign="middle" style="width:100px;">
                    <span style="display:inline-block;white-space:nowrap;padding:5px 12px;background-color:#fff2d5;border:1px solid #efdda8;border-radius:20px;color:#775214;font-size:12px;line-height:18px;font-weight:700;">待人工复核</span>
                  </td>
                </tr>
              </table>
              <p style="margin:0;font-size:15px;line-height:27px;color:#565a70;">{_html_text(paragraphs[0])}</p>
            </td></tr>
            <tr><td style="padding:24px 24px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#f7f8fc"
                     style="width:100%;table-layout:fixed;background-color:#f7f8fc;border:1px solid #e9ebf3;border-radius:10px;">
                <tr><td style="padding:18px 20px;word-break:break-all;overflow-wrap:anywhere;">
                  <p style="margin:0 0 6px;font-size:12px;line-height:20px;color:#686d84;">申请的 QQ 群</p>
                  <p style="margin:0;font-size:20px;line-height:28px;font-weight:700;color:#33364f;">{_html_text(group_id)}</p>
                </td></tr>
                <tr><td style="padding:16px 20px 18px;border-top:1px solid #e9ebf3;word-break:break-all;overflow-wrap:anywhere;">
                  <p style="margin:0 0 6px;font-size:12px;line-height:20px;color:#686d84;">初审标记原因</p>
                  <p style="margin:0;font-size:18px;line-height:30px;font-weight:700;color:#33364f;">{_html_text(reason)}</p>
                </td></tr>
              </table>
            </td></tr>
            <tr><td style="padding:24px;">
              <h2 style="margin:0 0 10px;font-size:16px;line-height:24px;font-weight:700;color:#33364f;">接下来怎么做</h2>
              <p style="margin:0 0 10px;font-size:15px;line-height:27px;font-weight:400;color:#33364f;">{_html_text(paragraphs[3])}</p>
              <p style="margin:0;font-size:15px;line-height:27px;font-weight:400;color:#33364f;">{_html_text(paragraphs[4])}</p>
            </td></tr>
            {contact_block}
          </table>
        </td></tr>
        <tr><td align="center" style="padding:18px 8px 0;font-size:12px;line-height:22px;color:#73788b;">{_html_text(paragraphs[-1])}</td></tr>
      </table>
      <!--[if mso]></td></tr></table><![endif]-->
    </td></tr>
  </table>
</body>
</html>"""
    return text, html
