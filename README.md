# nayntendoh – Nintendo Switch eShop ülke / fiyat takipçisi

Nintendo Switch eShop kataloğu ülkeden ülkeye değişir: bazı oyunlar sadece belirli
ülkelerde satılır, fiyatlar ve indirimler her ülkede farklıdır. Bu araç:

* üç bölgesel kataloğu (Avrupa, Amerika, Japonya) indirir,
* istediğiniz ülkelerin güncel fiyatlarını Nintendo'nun fiyat API'sinden çeker,
* her şeyi yerel bir SQLite veritabanında **fiyat geçmişiyle** birlikte saklar,
* ülke bazlı listeleme, arama, ülkeler arası karşılaştırma ve döviz çevirme sunar.

Her fiyat satırı için "bu fiyatı ilk gördüğüm tarih" ve "en son gördüğüm tarih"
tutulur. Böylece *"hangi ülkede hangi oyun var, en son şu tarihte fiyatı şuydu"*
sorusu doğrudan cevaplanır.

## Kurulum

### Hazır .exe (Python gerekmez)

GitHub Actions her push'ta Windows, Linux ve macOS için tek dosyalık portable
sürüm derler. İndirmek için:

1. Depoda **Actions** sekmesine girin, en son yeşil "Build portable executables" çalışmasını açın.
2. Sayfanın altındaki **Artifacts** bölümünden `eshop-windows-x64` dosyasını indirin ve zip'i açın.
3. `eshop.exe`'yi istediğiniz klasöre koyun; veritabanı (`eshop.sqlite3`) komutu çalıştırdığınız klasörde oluşur.

`v1.0` gibi bir etiket (tag) atıldığında aynı dosyalar otomatik olarak **Releases**
sayfasına da yüklenir.

`eshop.exe`'ye **çift tıklayınca** menülü etkileşimli mod açılır: numara seçerek
katalog indirebilir, fiyat güncelleyebilir, listeleyebilir ve karşılaştırabilirsiniz;
pencere siz çıkana kadar açık kalır. Aynı pencerede normal komutlar da yazılabilir.

Komut satırından kullanım Python sürümüyle aynıdır, sadece `python -m eshop` yerine `eshop.exe` yazılır:

```powershell
.\eshop.exe update --country DE GB US
.\eshop.exe list --country DE --on-sale --sort discount --convert TRY
```

**Japonca başlıklar**: Windows'un klasik konsol penceresi Japonca karakter içeren
yazı tipi kullanmaz. Program açılışta pencereyi UTF-8'e ve "MS Gothic" yazı tipine
geçirir; farklı bir yazı tipi için `ESHOP_FONT` ortam değişkenini kullanın
(`ESHOP_FONT=none` dokunmaz). Windows Terminal kullanıyorsanız buna gerek yoktur.

Kendiniz derlemek isterseniz Windows'ta `build.ps1` dosyasını çalıştırın.

### Kaynak koddan (Python)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m eshop --help
```

Python 3.10+ gerekir. Tek bağımlılık `requests`.

## Hızlı başlangıç

```bash
# 1) Katalogları indir (EU ~20k, US ~25k, JP ~15k oyun; ilk seferde 5-8 dakika)
python -m eshop catalog

# 2) İstediğin ülkelerin fiyatlarını çek (ülke başına ~1-2 dakika)
python -m eshop prices --country DE GB US JP PL

# (1 + 2 tek komutla: sadece gereken bölgelerin kataloğunu da indirir)
python -m eshop update --country DE GB

# 3) Listele
python -m eshop list --country DE --sort price --limit 30
python -m eshop list --country PL --on-sale --sort discount --convert TRY
python -m eshop list --country US --search zelda
python -m eshop list --country JP --platform "Switch 2" --format csv -o jp_switch2.csv

# 4) Ara ve karşılaştır
python -m eshop search "hollow knight"
python -m eshop compare "Tears of the Kingdom" --country DE GB PL US JP --fetch --convert TRY

# 5) Fiyat geçmişi
python -m eshop history 70010000063715 --country DE

# Ne var ne yok
python -m eshop status
python -m eshop countries
```

## Komutlar

| Komut | Açıklama |
|---|---|
| `countries` | Desteklenen ülkeler, para birimleri, hangi kataloğu kullandıkları ve veritabanındaki durum |
| `catalog [--region eu us jp] [--include-dlc]` | Oyun kataloğunu indir / güncelle |
| `prices --country … [--search X] [--workers N]` | Ülkelerin güncel fiyatlarını çek. `--country eu`, `americas`, `japan` veya `all` ile toplu |
| `update --country …` | `catalog` + `prices` |
| `list --country XX` | Ülkedeki oyunları en son fiyatlarıyla listele. Filtreler: `--search`, `--platform`, `--on-sale`, `--status all`; sıralama: `--sort title/price/price_desc/date/discount/updated`; `--convert TRY` ile ek sütun |
| `search METİN [--region]` | Yerel katalogda başlık / NSUID / ürün kodu ara |
| `compare SORGU [--country …] [--fetch] [--convert CUR]` | Bir oyunun fiyatını ülkeler arasında karşılaştır. `--fetch` o anda taze fiyat çeker |
| `history NSUID [--country XX]` | Fiyat değişiklik geçmişi |
| `status` | Veritabanı özeti |

Tüm liste komutları `--format table|csv|json` ve `-o dosya` destekler.
Veritabanı dosyası varsayılan olarak çalışma dizinindeki `eshop.sqlite3`; `--db` veya
`ESHOP_DB` ortam değişkeni ile değiştirilebilir.

## Nasıl çalışıyor?

* **Kataloglar**
  * Avrupa: `search.nintendo-europe.com` (Solr) – AU/NZ/ZA/RU dahil tüm "Avrupa" eShop'ları bu kataloğu kullanır.
  * Amerika: nintendo.com'un herkese açık Algolia arama indeksi. Algolia 1000 sonuçtan
    fazlasını sayfalamaya izin vermediği için katalog fiyat aralıklarına, gerekirse
    yayıncıya göre dilimlenerek indirilir.
  * Japonya: `search.nintendo.jp`.
* **Fiyatlar**: `https://api.ec.nintendo.com/v1/price?country=XX&ids=…` (istek başına 50 NSUID).
  Bir oyunun her bölgede farklı NSUID'si vardır; ülke → katalog eşlemesi `eshop/regions.py`'de.
  Avrupa ve Japonya katalogları ortak 5 harfli ürün kodu (örn. `HACPAXN7A` ↔ `AXN7A`) üzerinden
  birbirine bağlanır, böylece `compare` aynı oyunu bölgeler arasında eşleştirebilir.
  ABD kataloğu ürün kodu vermediği için ABD eşleşmesi başlık metniyle yapılır.
* **Geçmiş**: Aynı (oyun, ülke) için fiyat/durum değişmediyse yeni satır yazılmaz, mevcut
  satırın `last_seen` tarihi güncellenir. Değiştiyse yeni satır eklenir. Böylece geçmiş
  kompakt kalır.
* **Döviz**: `--convert` için ücretsiz Frankfurter API (ECB kurları) kullanılır, kurlar
  24 saat önbelleklenir. ECB'nin yayımlamadığı para birimleri (ARS, CLP, COP, PEN, RUB)
  için `n/a` görünür.

## Sınırlamalar

* **Türkiye'de resmi Nintendo eShop yoktur.** Fiyat API'si `country=TR` için her oyunu
  `not_found` döndürür; bu yüzden TR desteklenen ülkeler arasında değildir. Türkiye'den
  oyuncular genelde başka bir Avrupa ülkesinin mağazasını kullanır; `--convert TRY`
  ile tüm fiyatları TL karşılığıyla görebilirsiniz.
* Hong Kong / Kore / Tayvan katalogları henüz desteklenmiyor.
* Fiyatlar vergi dahil mağaza fiyatıdır; Gold Point / kampanya kodları hesaba katılmaz.
* Nintendo'nun uç noktaları resmî değildir ve değişebilir.
