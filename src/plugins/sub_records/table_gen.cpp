#include <cairo.h>
#include <pango/pangocairo.h>
#include <cstring>
#include <vector>
#include <jsoncpp/json/json.h>

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

    int cell_w = 150, cell_h = 45;
    int width  = cols * cell_w;
    int height = (rows + 1) * cell_h;

    cairo_surface_t* surf = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, width, height);
    cairo_t* cr = cairo_create(surf);

    // 背景白色
    cairo_set_source_rgb(cr, 1, 1, 1);
    cairo_paint(cr);

    cairo_set_source_rgb(cr, 0, 0, 0);
    cairo_set_line_width(cr, 1);

    // 创建 Pango 绘制模块
    PangoLayout* layout = pango_cairo_create_layout(cr);
    PangoFontDescription* font = pango_font_description_from_string(FONT_FAMILY " 14");

    pango_layout_set_font_description(layout, font);

    auto draw_text = [&](const char* txt, int x, int y){
        cairo_move_to(cr, x + 8, y + 10);
        pango_layout_set_text(layout, txt, -1);
        pango_cairo_show_layout(cr, layout);
    };

    // 绘制表头
    for(int c=0;c<cols;c++){
        int x=c*cell_w;
        cairo_rectangle(cr,x,0,cell_w,cell_h);
        cairo_stroke(cr);
        draw_text(headers[c].asCString(),x,0);
    }

    // 绘制内容
    for(int r=0;r<rows;r++){
        for(int c=0;c<cols;c++){
            int x=c*cell_w, y=(r+1)*cell_h;
            cairo_rectangle(cr,x,y,cell_w,cell_h);
            cairo_stroke(cr);
            draw_text(data[r][c].asCString(),x,y);
        }
    }

    // PNG → 内存
    std::vector<unsigned char> buffer;
    cairo_surface_write_to_png_stream(
        surf,
        [](void* closure,const unsigned char* data,unsigned len){
            auto* vec=(std::vector<unsigned char>*)closure;
            vec->insert(vec->end(),data,data+len);
            return CAIRO_STATUS_SUCCESS;
        }, &buffer
    );

    *out_len = buffer.size();
    unsigned char* ret=(unsigned char*)malloc(buffer.size());
    memcpy(ret,buffer.data(),buffer.size());

    pango_font_description_free(font);
    g_object_unref(layout);
    cairo_destroy(cr);
    cairo_surface_destroy(surf);
    return ret;
}

extern "C" void free_png_buffer(void* p){ free(p); }

} // extern "C"
