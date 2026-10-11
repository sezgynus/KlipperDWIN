# LCD görselleri

[English](README.md) · [Türkçe](README_TR.md) · [Katkı](../CONTRIBUTING_TR.md)

## Bu klasördeki dosyalar

| Dosya | Amaç |
|---|---|
| `klipperdwin_bootsplash.jpg` | Panel picture slot 0 için seçilen açılış görseli |
| `spool-empty.png` | Ortak 42×52 boş makara sprite’ı: ahşap kenarlar ve ince gri merkez |
| `display-settings.png` | Özgün şeffaf Display ikon sprite'ı |
| `klipperdwin-readme.png` | Açılış görselinden uyarlanan README logo ve yazı başlığı |
| [emulator/](emulator/README_TR.md) | Ekran görüntüleri için bilgisayar tarafı stok ikon ve font girdileri |

Açılış JPEG’i panelin 0 numaralı resim slotu için 480×272 boyutundadır. Önbellek kopyası olmadan doğrudan gösterilir.

## Yönetilen ikon kütüphanesi

Baseline JPEG ikonlarını dosya adında ikon ID’siyle [`assets/icons`](icons/README_TR.md) klasörüne koyun. Uygulama güncelleme sonrası ilk LCD bağlantısında değişen kaynakları paketleyip yükler. Paketleyici blok boşluklarını kullanır ve her bloğun son baytını boş bırakır. Emülatör aynı kaynakları kullanır.

## Ekran görüntüleri

Kullanıcı arayüzü ekran görüntüleri bu görsel klasörüne değil `docs/assets/screens/` içine aittir. [Görüntü alma rehberini](../docs/ui-emulator_TR.md) izleyin ve özgün 272×480 PNG çıktısını koruyun.

## Panel kaynaklarını yeniden yükledikten sonra

Panel kaynaklarını yeniden kurduktan sonra yönetilen ikonları SSH üzerinden servis kullanıcısı olarak zorla yeniden yükleyin:

```bash
sudo systemctl stop KlipperDWIN.service
~/klipperdwin-env/bin/python ~/KlipperDWIN/tools/reload_icons.py
sudo systemctl start KlipperDWIN.service
```

Araç yapılandırılmış UART’ı okur, kütüphane 7’yi oluşturup bloklarını yeniden yükler. Ekran ayarları korunur.
