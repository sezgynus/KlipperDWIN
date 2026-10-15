# LCD görselleri

[English](README.md) · [Türkçe](README_TR.md) · [Katkı](../CONTRIBUTING_TR.md)

## Bu klasördeki dosyalar

| Dosya | Amaç |
|---|---|
| `petrel_bootsplash.jpg` | Panel resim slotu 0 için Petrel kuş logosu ve sloganıyla açılış görseli |
| `petrel_shared.jpg` | Slot 1 ortak görsel sayfası; portre görünümün sol üstünde proje QR kodu |
| `spool-empty.png` | Ortak 42×52 boş makara sprite’ı: ahşap kenarlar ve ince gri merkez |
| `display-settings.png` | Özgün şeffaf Display ikon sprite'ı |
| `petrel-readme.png` | İki ana README için Petrel kuş logosu, yazı ve slogan başlığı |
| [emulator/](emulator/README_TR.md) | Ekran görüntüleri için bilgisayar tarafı stok ikon ve font girdileri |
| [stock-dwin/](stock-dwin/README_TR.md) | Stok LCD firmware'ini ve görsellerini geri yüklemek için orijinal Creality DWIN_SET paketi |

Açılış JPEG’i panelin 0 numaralı resim slotu için 480×272 boyutundadır. Önbellek kopyası olmadan doğrudan gösterilir. Açılış görselinin senkronizasyonundan sonra bootsplash, ilerleme çubuğu ve yükleniyor animasyonu ikon kütüphanesi hazırlığı ve kontrollerinden önce gösterilir. Değişiklik yoksa ikon senkronizasyonu animasyonu durdurmaz; gerçek ikon yüklemesinde geçici olarak durdurulur ve sonraki açılış aşamasında yeniden başlatılır.

Değişen açılış görseli ilk LCD bağlantısında otomatik olarak resim slotu 0’a yüklenir. Flash adresi `0x0120` üzerindeki doğrulanmış parmak izi tekrar yazmayı önler; JPEG baseline 480×272 biçiminde ve en fazla 32767 bayt olmalıdır.

## Ortak UI görsel sayfası

`petrel_shared.jpg`, Picture Flash **slot 1** içinde saklanır. JPEG kaynaklarını [`assets/shared-artwork`](shared-artwork/README_TR.md) klasörüne koyup `python tools/pack_shared_artwork.py` çalıştırın. Araç kaynakları portre **272×480** sayfaya kompakt biçimde yerleştirir ve dosya adlarından `shared_artwork_layout.py` içinde `QR_BOX` / `QR_SIZE` gibi tanımlar üretir. Geometrik sınır ve son JPEG'in **32767 bayt** sınırı doğrulanır; taşma varsa mevcut çıktılar korunur. Fiziksel çıktı **480×272**, baseline 4:2:0 JPEG'dir.

QR ICO kütüphanesinde yer almaz; Info kaynak koordinatlarını ve boyutunu üretilen tanımlardan alır. `python tools/render_project_qr.py` yalnız `qr.jpg` kaynağını ve SVG'sini yeniler (geliştirme bağımlılığı: CairoSVG); ardından genel paketleyiciyi çalıştırın. Yeni görseller için QR üreticisini çalıştırmak gerekmez. Kaynakları, JPEG sayfasını ve yerleşim modülünü birlikte commit edin; servis JPEG/yerleşim SHA-256 uyuşmazlığını reddeder.

Değişen sayfa ilk LCD bağlantısında otomatik yüklenir; Data Flash `0x0150–0x0177` parmak izi değişmeyen dosyanın tekrar yazılmasını önler. Info açılırken sayfa ekranı değiştirmeden Area 1’e açılır; kaydırmada yalnız yeni görünen QR bölgesi opak olarak kopyalanır. Başka bir resim Area 1’i değiştirirse veya LCD yeniden bağlanırsa önbellek yeniden hazırlanır.

## Yönetilen ikon kütüphanesi

Baseline JPEG ikonlarını dosya adında ikon ID’siyle [`assets/icons`](icons/README_TR.md) klasörüne koyun. Uygulama güncelleme sonrası ilk LCD bağlantısında değişen kaynakları paketleyip yükler. Paketleyici blok boşluklarını kullanır ve her bloğun son baytını boş bırakır. Emülatör aynı kaynakları kullanır.

Print butonları, switchler, fan kareleri, kaynak lisansları ve mevcut paket boyutu ile ayrılan alanın farkı [ikon kaynak rehberinde](icons/README_TR.md#print-butonları-switchler-ve-fan-görselleri) açıklanır.

## Ekran görüntüleri

Kullanıcı arayüzü ekran görüntüleri bu görsel klasörüne değil `docs/assets/screens/` içine aittir. [Görüntü alma rehberini](../docs/ui-emulator_TR.md) izleyin ve özgün 272×480 PNG çıktısını koruyun.

## Panel kaynaklarını yeniden yükledikten sonra

Panel kaynaklarını yeniden kurduktan sonra yönetilen ikonları SSH üzerinden servis kullanıcısı olarak zorla yeniden yükleyin:

```bash
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/reload_icons.py
sudo systemctl start Petrel.service
```

Araç yapılandırılmış UART’ı okur, kütüphane 3’yi oluşturup bloklarını ve ortak slot-1 sayfasını yeniden yükler. Ekran ayarları korunur.
