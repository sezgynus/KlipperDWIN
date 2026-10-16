# Emülatör ekran görüntüleri

[English](ui-emulator.md) · [Türkçe](ui-emulator_TR.md) · [Katkı](../CONTRIBUTING_TR.md)

## Ne işe yarar

İsteğe bağlı emülatör, çalışan Petrel servisinin çizdiği ekranları yakalar. Yerleşimleri incelemek, dokümantasyonu yenilemek ve görsel hataları özgün boyutlu görsellerle bildirmek için kullanın. Gerçek LCD arayüzünü takip eder; bağımsız yazıcı simülatörü veya canlı tarayıcı görüntüleyicisi değildir. Fiziksel encoderle gezinin, ardından SSH üzerinden görüntü isteyin.

## Açma veya kapatma

Bağımlılıklar normal kurulum ve Moonraker güncellemelerine dahildir. `~/.config/Petrel/Petrel.env` içinde varsayılanı değiştirin:

```ini
PETREL_EMULATOR=1
```

Ardından yeniden başlatın:

```bash
sudo systemctl restart Petrel.service
```

Kapatmak için `PETREL_EMULATOR=0` yapıp yeniden başlatın. Kurulum/yapılandırma tekrarlandığında mevcut açık değer korunur. `./configure.sh`, özel font, socket ve ekran görüntüsü klasörü anahtarlarını da korur. Eski kurulumda bağımlılıklar eksikse:

```bash
cd ~/Petrel
~/petrel-env/bin/python -m pip install -r requirements.txt
```

## SSH üzerinden görüntü alma

1. LCD'de istediğiniz ekranı açın ve çizimin bitmesini bekleyin.
2. SSH içinde **servis kullanıcısıyla, sudo kullanmadan** çalıştırın:

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py
```

Komut kayıt yolunu yazdırır. Görseller varsayılan olarak `~/Petrel-screenshots/` içine zaman damgalı, benzersiz adlarla kaydedilir. Çıktı yeniden boyutlandırılmamış, kayıpsız **272×480 RGB PNG**'dir. Otomatik görüntü kaydedilmez.

BMP çıktısı için:

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py --format bmp
```

İncelemek için görselleri bilgisayarınıza kopyalayın. Repo ekran görüntüleri, ekranı/durumu anlatan adlarla `docs/assets/screens/` içine konur.

## Ek ayarlar

Aynı harici ortam dosyasına yazıp servisi yeniden başlatın:

| Değişken | Amaç |
|---|---|
| `PETREL_SCREENSHOT_DIRECTORY` | Özel çıktı klasörü |
| `PETREL_EMULATOR_SOCKET` | Özel yerel görüntü soketi; varsayılan `~/.cache/Petrel-emulator/control.sock` |
| `PETREL_EMULATOR_FONT` | Özelleştirilmiş fiziksel panelle eşleşen font dosyası |

Özel sokette görüntü komutuna aynı yolu verin:

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py --socket /path/to/control.sock
```

## Sorun giderme ve sınırlar

| Sorun | Yapılacak işlem |
|---|---|
| Bağlanamıyor veya izin reddediliyor | `PETREL_EMULATOR=1` kontrol edin, servisi yeniden başlatın, servis kullanıcısıyla çalıştırın ve soket yolunu kontrol edin |
| Görüntü reddediliyor | Panel bağlantısını, yüklenen kaynakları ve servis günlüğünü kontrol edin; tamamlanmış ekranı bekleyin |
| Yazı/ikonlar panelden farklı | Font/ikon dosyalarını karşılaştırın; [emülatör kaynaklarına](../assets/emulator/README_TR.md) bakın |
| Kısma görselde görünmüyor | Görüntüler fiziksel arka ışık parlaklığını değil ekran piksellerini gösterir |

Emülatör LCD belleğini okumak yerine çizim komutlarını takip eder. Fontlar, JPEG çözümü ve QR deseni fiziksel panelden farklı olabilir. Bu sorunlarda hem ekran görüntüsü hem fotoğraf paylaşın; tek başına görüntü fiziksel ekran doğruluğunu kanıtlamaz.

## Dokümantasyon ekranlarını çevrimdışı üretme

Bir geliştirme checkout’u içinde tüm dokümantasyon ekranlarını gerçek UI çizimleriyle yeniden üretebilirsiniz. Aracın örnek yazıcı ve MMU verileri kullandığı bu işlem fiziksel yazıcıya bağlanmaz; çalışan servis veya UART bağlantısı gerektirmez. Normal kurulum bağımlılıkları yeterlidir; repodaki `tests/` klasörü bulunmalıdır.

```bash
cd ~/Petrel
~/petrel-env/bin/python tools/render_docs_screenshots.py --frame
```

Tüm ekranlar başarılı çizilirse `docs/assets/screens/` içindeki görseller yenilenir. Mevcut dosya adlarını koruyun; forumlar bu adlara dış bağlantı verebilir. Yeni bir ekran eklemek için aracın sahne listesine örnek durumu ve iki dilde açıklamasını ekleyin. Galerileri de aynı listeden yeniden üretir.

Repo dosyalarını değiştirmeden incelemek için:

```bash
~/petrel-env/bin/python tools/render_docs_screenshots.py --output-directory /tmp/petrel-docs-screens
```

Örnek değerleri ve kullanılabilir ekranları [galeride](screenshots_TR.md) görebilirsiniz. Gerçek bir hatayı raporlarken yukarıdaki canlı servis yakalama yöntemini kullanın.

İsteğe bağlı `--frame`, ekran görüntüsünü fiziksel ekran çerçevesinin içine yerleştirir. Parametre verilmezse 272×480 çıktı değişmez.

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py --frame
```

### PNG, çerçeve ve GIF yenileme

Tek üretim oturumunda aynı checkout'tan bütün çıktıları yenileyin:

```bash
~/petrel-env/bin/python tools/render_docs_screenshots.py --frame
~/petrel-env/bin/python tools/render_print_controls.py
~/petrel-env/bin/python tools/render_print_controls.py --frame
~/petrel-env/bin/python tools/render_docs_workflows.py
```

İlk komut özgün 272×480 panel PNG'lerini ve `docs/assets/screens/framed/` içindeki 528×900 sunum kopyalarını üretir; aynı UI pikselleri çerçeveye yeniden örneklenmeden yerleştirilir. İki galeri aynı sahne kaydından, aynı menü sırasıyla yenilenir. Repo içindeki varsayılan hedefe üretirken `--frame` yazılmasa da çerçeveli kopyalar yenilenir. Bütün sahneler ve çerçeveler hazırlanıp başarıyla tamamlanmadan mevcut panel dosyaları değiştirilmez. Özel `--output-directory` hedefi ise yalnız `--frame` istenirse çerçeve üretir. Mevcut 76 dosya adı korunur; yeni sahneler eklenir.

İkinci/üçüncü komut Print/Tune başarı akışını özgün/çerçeveli GIF olarak üretir. Son komut güç basılı tutma/iptal/engelleme, iki kırmızı ret yanıp sönmesi, uzun MMU hatası kaydırması ve 0/1/50/100% panel-native fan animasyonu için iki biçimde GIF üretir. Özgün GIF'ler `docs/assets/`, sunum kopyaları `docs/assets/framed/` içindedir. PNG komutu bu GIF'leri yenilemez.

Bütün durumlar gerçek UI/driver ile örnek verilerden üretilir; fiziksel yazıcıya bağlanılmaz. Hata yanıtları test doubles ile sağlanır. Saat 12:34'tür; animasyonlar kontrollü geçen zamanla örneklenir. Eksik preview/katman, azaltılmış Tune ve uzun hata örnekleri galeriye dahildir. Fan GIF'i panel animasyon komutlarını emüle eder; fiziksel JPEG decoder doğrulaması yerine geçmez.


## İsteğe bağlı canlı Remote Display (8088 portu)

Çalışan DWIN emülatörü artık tarayıcıda **canlı görüntü** sunabilir. Mouse tekerleği normal enkoder dönüşlerini, **orta tuşa tıklama** kısa enkoder basışını üretir. Gerçek LCD/enkoder kullanılmaya devam eder. Ek UART, Moonraker bağlantısı veya ekran görüntüsü dosyası üretilmez.

Özelliği `~/.config/Petrel/Petrel.env` dosyasında aç:

```ini
PETREL_REMOTE=1
PETREL_REMOTE_PORT=8088
```

Yazıcı güvenli şekilde boşta iken yalnızca **Petrel.service** servisini yeniden başlat. `PETREL_REMOTE=1` mevcut emülatörü otomatik açar; ayrıca `PETREL_EMULATOR=1` yazmak gerekmez. Sunucu **yalnız 127.0.0.1:8088** adresini dinler. Yazıcıyı kontrol edebildiğinden bilerek `0.0.0.0` üzerinde açılmaz. Başka bir bilgisayardan güvenli erişim için SSH tüneli kur:

```bash
ssh -N -L 8088:127.0.0.1:8088 sezgynpi@<pi-adresi>
```

Ardından o bilgisayarın tarayıcısında **http://127.0.0.1:8088** adresini aç. Pi üstünde de aynı adres doğrudan kullanılabilir. 8088 portunu açık internete yönlendirme veya kimlik doğrulama/iletişim koruması olmadan ters proxy arkasına koyma. Görüntü açıkken yaklaşık 250 ms'de bir yerel 272×480 JPEG alınır; enkoder girdileri mevcut UI olay kuyruğuna eklenir ve LCD/oturum uygun değilse reddedilir. Orta tuşu basılı tutmak güvenlik gereği güç uzun basışını simüle **etmez**. Görüntüden fan, buzzer veya LED'in fiziksel olarak çalıştığı kanıtlanamaz.

Kapatmak için `PETREL_REMOTE=0` yapıp Petrel'i yeniden başlat. Port doluysa `PETREL_REMOTE_PORT` değerini değiştirip SSH tünelini de aynı porta uyarla. Mevcut `PETREL_EMULATOR` ve Unix screenshot servisi bağımsız çalışmaya devam eder.
