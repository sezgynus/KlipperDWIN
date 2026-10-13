# Testler ve donanım doğrulaması

[English](README.md) · [Türkçe](README_TR.md) · [Katkı](../CONTRIBUTING_TR.md)

## Otomatik kontrolleri çalıştırma

Uygulama bağımlılıkları kurulu olarak repo kökünden:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q .
```

Kurulu Pi'de `python3` yerine `~/petrel-env/bin/python` kullanın. Testler izole durum ve taklit seri/GPIO/ağ bağlantıları kullanır. Yazıcıya bağlanmaz veya hareket ettirmez. Yerel Unix soket testleri bunlara izin veren ortam gerektirir; aksi durumda ilgili entegrasyon kontrolleri atlanır.

## Test kapsamı

- Menüler, encoder gezinmesi, sayısal düzenlemeler ve özellik kullanılabilirliği.
- Dosya tarama, önizleme, sıralama ve baskı kontrolleri.
- Hareket kısıtları, sıcaklık presetleri ve kalibrasyon kayıt/iptal davranışı.
- MMU işlemleri, eşlemeler, kurtarma, LED'ler ve çoklu üniteler.
- Ekran ayarları, güç/açılış davranışı ve yeniden bağlantı.
- Emülatör çizimi, görüntü istekleri ve kayıpsız çıktı.

Davranış değişikliğinde kullanıcı sonucu ve hata durumları için kontroller ekleyin veya güncelleyin. Başarılı testler fiziksel çizim, hareket, ölçüm doğruluğu veya harici servislerde kalıcı kaydı kanıtlamaz. GitHub regresyon iş akışı `master` ve tanımlı özellik dallarında çalışır; diğer dallarda da yerel komutu kullanın.

## Donanım doğrulaması

Değişikliğinizle ilgili kontrolleri seçip revizyonu, donanımı ve sonucu kaydedin:

| Alan | Gerçek kurulumda kontrol |
|---|---|
| Gezinme/ekran | Sayfa seçimi, Back, sayısal düzenleme, okunaklı ikon/yazı, parlaklık, kısma ve uyandırma girdisi |
| Baskı | Klasör ve sıralama değişimleri, eksik önizleme verisi, doğru dosya seçimi, Pause/Resume/Stop |
| Hareket/ısı | Home edilmiş hareket, ekstrüzyon sıcaklık kısıtları, preset kayıt/uygulama ve jog kurtarma |
| Kalibrasyon | Vida yönleri/sonuçları, mesh yönü, kayıt/yeniden başlatma ve açık durdurma/shutdown |
| MMU | Kanal/takım hedefi, load/unload/eject/bypass, eşleme taslakları, kurtarma, sensörler, LED çıktısı ve ünite seçimi |
| Güç/açılış | Basılı tutarak açma, kapatma onayı, röle döngüsü, açılış ilerlemesi ve temiz ana ekran dönüşü |
| Görüntüler | Yapılandırılmış font/ikonlar dahil görüntüyü fiziksel panelle karşılaştırma |

Bağlantı kesilmesi veya belirsiz işlem sonrası gerçek durumu doğrulayın ve önceki komutun otomatik tekrarlanmadığını kontrol edin. Hataları günlük ve görüntü/fotoğrafla paylaşın. Beklenen davranış için [kullanıcı rehberine](../docs/user-guide_TR.md), [MMU rehberine](../docs/mmu-guide_TR.md) ve [LCD uyumluluğuna](../docs/lcd-assets_TR.md) bakın.

## Print/Tune ve görsel kaynak sözleşmeleri

| Kontrol | Mevcut test kaynağı | Fiziksel doğrulama |
|---|---|---|
| 17 alan, birimler, capability ve politika pinleri | `test_print_tuning.py` | Yapılandırmaya göre alanlar; switch yalnız politika değiştirir |
| Sessiz düzenleme ve baskı akışı | `test_print_focus.py`, `test_print_screen.py` | Ret/geri dönüş, iki kırmızı yanıp sönme, geç yanıt, yeniden bağlantı, Pause/Resume ve Stop onayı |
| Güç kısayolu | `test_power_shortcut.py` | 450 ms gecikme, 1.2 s kapatma/2 s açma ayrımı, yarım hold, korunmuş Tune taslağı, aktif/paused baskıda engel |
| JPEG/font ve buton kaynakları | `test_lcd_assets.py`, `test_native_custom_icons.py` | Font ID 0, 4:2:0, iki durumda aynı buton maskesi, seçimden kalan piksel olmaması |
| Paketleme/senkronizasyon | `test_icon_library_packing.py`, `test_managed_icon_library.py` | Kaynak/export denkliği, library 3, yeniden yüklemeden sonra ikonlar |

Yeni senaryolar için [galeriyi](../docs/screenshots_TR.md) ve [PNG/GIF yeniden üretimini](../docs/ui-emulator_TR.md#png-çerçeve-ve-gif-yenileme) kontrol edin. Başlık/satır sayısı EN/TR anlam denkliğini kanıtlamaz; özellikler, uyarılar, komut blokları, birimler ve görsel sırası da incelenmelidir.
