# LCD görselleri

[English](README.md) · [Türkçe](README_TR.md) · [Katkı](../CONTRIBUTING_TR.md)

## Bu klasördeki dosyalar

| Dosya | Amaç |
|---|---|
| `petrel_bootsplash.jpg` | Panel resim slotu 0 için Petrel kuş logosu ve sloganıyla açılış görseli |
| `spool-empty.png` | Ortak 42×52 boş makara sprite’ı: ahşap kenarlar ve ince gri merkez |
| `display-settings.png` | Özgün şeffaf Display ikon sprite'ı |
| `petrel-readme.png` | İki ana README için Petrel kuş logosu, yazı ve slogan başlığı |
| [emulator/](emulator/README_TR.md) | Ekran görüntüleri için bilgisayar tarafı stok ikon ve font girdileri |

Açılış JPEG’i panelin 0 numaralı resim slotu için 480×272 boyutundadır. Önbellek kopyası olmadan doğrudan gösterilir. Açılış görselinin senkronizasyonundan sonra bootsplash, ilerleme çubuğu ve yükleniyor animasyonu ikon kütüphanesi hazırlığı ve kontrollerinden önce gösterilir. Değişiklik yoksa ikon senkronizasyonu animasyonu durdurmaz; gerçek ikon yüklemesinde geçici olarak durdurulur ve sonraki açılış aşamasında yeniden başlatılır.

Değişen açılış görseli ilk LCD bağlantısında otomatik olarak resim slotu 0’a yüklenir. Flash adresi `0x0120` üzerindeki doğrulanmış parmak izi tekrar yazmayı önler; JPEG baseline 480×272 biçiminde ve en fazla 32767 bayt olmalıdır.

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

Araç yapılandırılmış UART’ı okur, kütüphane 3’yi oluşturup bloklarını yeniden yükler. Ekran ayarları korunur.
