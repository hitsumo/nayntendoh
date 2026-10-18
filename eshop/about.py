"""Program description shown by `eshop about` and the interactive menu."""

from . import __author__, __url__, __version__

ABOUT = f"""
eshop {__version__} – Nintendo Switch eShop ülke / fiyat takipçisi

Ne yapar?
  Nintendo Switch eShop mağazası ülkeden ülkeye farklıdır: bazı oyunlar yalnızca
  belirli ülkelerde satılır, fiyatlar ve indirimler her ülkede başka olur. Bu
  program üç bölgesel kataloğu (Avrupa, Amerika, Japonya) indirir, 43 ülkenin
  güncel fiyatlarını Nintendo'nun fiyat servisinden çeker ve hepsini bilgisayarınızdaki
  bir veritabanında fiyat geçmişiyle birlikte saklar.

Neler yapabilirsiniz?
  • Bir ülkedeki tüm oyunları fiyatlarıyla listeleme, indirimdekileri süzme
  • Oyun arama ve aynı oyunun ülkeler arası fiyat karşılaştırması
  • Fiyatları TL'ye (veya başka bir para birimine) çevirip sıralama
  • Bir oyunun fiyat geçmişini görme: hangi fiyat hangi tarihler arasında geçerliydi
  • Sonuçları CSV / JSON olarak dışa aktarma

Veri kaynakları
  Kataloglar: nintendo.com (Amerika), nintendo.co.uk (Avrupa), nintendo.co.jp (Japonya)
  Fiyatlar:   api.ec.nintendo.com   Kurlar: Avrupa Merkez Bankası (frankfurter.dev)
  Bu program Nintendo ile bağlantılı değildir; veriler herkese açık servislerden alınır.

Yazar
  {__author__} · {__url__}
  Kaynak kod: https://github.com/hitsumo/nayntendoh
"""


def text() -> str:
    return ABOUT.strip("\n")
