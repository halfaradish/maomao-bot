#include <cairo.h>
#include <cstring>
#include <vector>
#include <json/json.h>
#ifdef __linux__
    #define FONT_NAME "Noto Sans CJK SC"
#else
    #define FONT_NAME "Microsoft YaHei"
#endif
extern "C" {

// 主生成函数
unsigned char* generate_table_png(const char* json_str, int* out_len) {
    Json::Value root;
    Json::Reader reader;
    if (!reader.parse(json_str, root)) return nullptr;

    int rows = root["rows"].asInt();
    int cols = root["cols"].asInt();
    const Json::Value& headers = root["headers"];
    const Json::Value& data    = root["data"];

    int cell_w = 120, cell_h = 40;
    int width  = cols * cell_w;
    int height = (rows + 1) * cell_h;

    cairo_surface_t* surf = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, width, height);
    cairo_t* cr = cairo_create(surf);

    // 白色背景
    cairo_set_source_rgb(cr, 1, 1, 1);
    cairo_paint(cr);

    // 黑色边框 + 文字
    cairo_set_source_rgb(cr, 0, 0, 0);
    cairo_set_line_width(cr, 1);
    // 自动切换字体
    cairo_select_font_face(cr, FONT_NAME,
                           CAIRO_FONT_SLANT_NORMAL,
                           CAIRO_FONT_WEIGHT_NORMAL);
    cairo_set_font_size(cr, 14);

    auto draw_text = [&](const char* text, int x, int y) {
        cairo_move_to(cr, x + 5, y + 25);
        cairo_show_text(cr, text);
    };

    // 表头
    for (int c = 0; c < cols; ++c) {
        int x = c * cell_w;
        cairo_rectangle(cr, x, 0, cell_w, cell_h);
        cairo_stroke(cr);
        draw_text(headers[c].asCString(), x, 0);
    }

    // 数据行
    for (int r = 0; r < rows; ++r) {
        for (int c = 0; c < cols; ++c) {
            int x = c * cell_w;
            int y = (r + 1) * cell_h;
            cairo_rectangle(cr, x, y, cell_w, cell_h);
            cairo_stroke(cr);
            draw_text(data[r][c].asCString(), x, y);
        }
    }

    // 一次性写入内存 PNG
    std::vector<unsigned char> buffer;
    cairo_surface_write_to_png_stream(
        surf,
        [](void* closure, const unsigned char* data, unsigned int length) -> cairo_status_t {
            auto* vec = static_cast<std::vector<unsigned char>*>(closure);
            vec->insert(vec->end(), data, data + length);
            return CAIRO_STATUS_SUCCESS;
        },
        &buffer
    );

    *out_len = buffer.size();
    unsigned char* ret = (unsigned char*)malloc(buffer.size());
    memcpy(ret, buffer.data(), buffer.size());

    cairo_destroy(cr);
    cairo_surface_destroy(surf);
    return ret;
}

// 供 Python 释放内存
extern "C" void free_png_buffer(void* ptr) {
    free(ptr);
}

} // extern "C"