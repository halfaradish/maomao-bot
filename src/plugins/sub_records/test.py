import asyncio
from table_generator import generate_table_png_bytes

async def main():
    headers = ["Name", "Age", "City"]
    rows = [
        ["Alice", "23", "Tokyo"],
        ["Bob", "20", "Osaka"],
        ["Chris", "25", "Nagoya"]
    ]

    png = await generate_table_png_bytes(headers, rows)
    with open("test_linux.png", "wb") as f:
        f.write(png)

asyncio.run(main())
print("Linux 生成成功 ✔ 输出 test_linux.png")
