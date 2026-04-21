import datetime

from scripts.court_sites_scraper import extract_fields, clean_text


def test_extract_fields_basic():
    html = """
    <html>
      <head><title>Мировой судья судебного участка № 1</title></head>
      <body>
        <h1>Судебный участок № 1 Автозаводского района</h1>
        <div>Адрес: 603950, г. Нижний Новгород, ул. Ватутина, д. 10А</div>
        <div>Телефон: +7 (831) 299-47-10</div>
        <div>E-mail: msud1.nnov@sudrf.ru</div>
        <div>График работы: Пн-Чт 8:00-17:00</div>
        <p>Описание границ участка: от проспекта Ленина до улицы Плотникова...</p>
      </body>
    </html>
    """
    res = extract_fields(html, "https://example.com")
    assert "участок" in res.name.lower()
    assert "ватутина" in res.address.lower()
    assert res.phone.endswith("2994710")
    assert res.email == "msud1.nnov@sudrf.ru"
    assert "8:00" in res.schedule
    assert res.section_numbers == ["1"]
    assert "границ" in res.boundary_snippet.lower()
    # fetched_at isoformat
    datetime.datetime.fromisoformat(res.fetched_at)


def test_clean_text_removes_extra_spaces():
    assert clean_text("  a   b  ") == "a b"
