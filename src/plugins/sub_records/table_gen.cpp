#include <cairo.h>
#include <pango/pangocairo.h>
#include <cstring>
#include <vector>
#include <string>
#include <json/json.h>

#ifdef __linux__
#define FONT_FAMILY "Noto Sans CJK SC"
#else
#define FONT_FAMILY "Microsoft YaHei"
#endif

extern "C" {

unsigned char* generate_table_png(const char* json_str, int* out_len) {
    Json::Value root;
    Json::Reader reader;
    if (!reader.parse(json_str, root)) return nullptr;

    int rows = root["rows"].asInt();
    int cols = root["cols"].asInt();
    auto headers = root["headers"];
    auto data    = root["data"];

    // ===== 样式常量配置 =====
    int cell_w = 150;      // 单元格宽度
    int cell_h = 50;       // 单元格高度 (稍微加高增加呼吸感)
    int margin = 24;       // 画布外边距

    int width  = cols * cell_w + margin * 2;
    int height = (rows + 1) * cell_h + margin * 2;

    cairo_surface_t* surf = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, width, height);
    cairo_t* cr = cairo_create(surf);

    // 1. 绘制全局纯白背景
    cairo_set_source_rgb(cr, 1.0, 1.0, 1.0);
    cairo_paint(cr);

    // 创建 Pango 绘制模块
    PangoLayout* layout = pango_cairo_create_layout(cr);

    // 辅助函数：绘制绝对居中的文字
    auto draw_centered_text = [&](const char* txt, int x, int y, int w, int h, const char* font_str, double r, double g, double b) {
        PangoFontDescription* font = pango_font_description_from_string(font_str);
        pango_layout_set_font_description(layout, font);
        pango_layout_set_text(layout, txt, -1);

        int text_w, text_h;
        pango_layout_get_pixel_size(layout, &text_w, &text_h);

        cairo_set_source_rgb(cr, r, g, b);
        // 精确计算居中坐标
        cairo_move_to(cr, x + (w - text_w) / 2.0, y + (h - text_h) / 2.0);
        pango_cairo_show_layout(cr, layout);
        pango_font_description_free(font);
    };

    // 2. 绘制表头 (深蓝灰色背景 #2C3E50)
    for(int c = 0; c < cols; c++){
        int x = margin + c * cell_w;
        int y = margin;

        // 填充表头背景
        cairo_set_source_rgb(cr, 44.0/255.0, 62.0/255.0, 80.0/255.0);
        cairo_rectangle(cr, x, y, cell_w, cell_h);
        cairo_fill(cr);

        // 绘制表头文字 (白色, 加粗, 14号)
        std::string font_str = std::string(FONT_FAMILY) + " Bold 14";
        draw_centered_text(headers[c].asCString(), x, y, cell_w, cell_h, font_str.c_str(), 1.0, 1.0, 1.0);
    }

    // 3. 绘制数据行
    std::string row_font_str = std::string(FONT_FAMILY) + " 13";
    for(int r = 0; r < rows; r++){
        int y = margin + (r + 1) * cell_h;

        // 交替斑马纹背景
        if (r % 2 == 0) {
            // 偶数行使用浅灰色 #F8F9FA
            cairo_set_source_rgb(cr, 248.0/255.0, 249.0/255.0, 250.0/255.0);
        } else {
            // 奇数行使用纯白色
            cairo_set_source_rgb(cr, 1.0, 1.0, 1.0);
        }
        cairo_rectangle(cr, margin, y, cols * cell_w, cell_h);
        cairo_fill(cr);

        // 绘制行底部浅灰分割线 #DEE2E6 (去除垂直线，显得更干净)
        cairo_set_source_rgb(cr, 222.0/255.0, 226.0/255.0, 230.0/255.0);
        cairo_set_line_width(cr, 1.0);
        cairo_move_to(cr, margin, y + cell_h);
        cairo_line_to(cr, margin + cols * cell_w, y + cell_h);
        cairo_stroke(cr);

        // 绘制数据文字 (深灰色 #212529)
        for(int c = 0; c < cols; c++){
            int x = margin + c * cell_w;
            draw_centered_text(data[r][c].asCString(), x, y, cell_w, cell_h, row_font_str.c_str(), 33.0/255.0, 37.0/255.0, 41.0/255.0);
        }
    }

    // 4. 绘制整个表格的外边框线
    cairo_set_source_rgb(cr, 222.0/255.0, 226.0/255.0, 230.0/255.0);
    cairo_set_line_width(cr, 1.5);
    cairo_rectangle(cr, margin, margin, cols * cell_w, (rows + 1) * cell_h);
    cairo_stroke(cr);

    // PNG → 内存输出逻辑保持不变
    std::vector<unsigned char> buffer;
    cairo_surface_write_to_png_stream(
        surf,
        [](void* closure, const unsigned char* data, unsigned len){
            auto* vec = (std::vector<unsigned char>*)closure;
            vec->insert(vec->end(), data, data + len);
            return CAIRO_STATUS_SUCCESS;
        }, &buffer
    );

    *out_len = buffer.size();
    unsigned char* ret = (unsigned char*)malloc(buffer.size());
    memcpy(ret, buffer.data(), buffer.size());

    g_object_unref(layout);
    cairo_destroy(cr);
    cairo_surface_destroy(surf);
    return ret;
}

extern "C" void free_png_buffer(void* p){ free(p); }

} // extern "C"