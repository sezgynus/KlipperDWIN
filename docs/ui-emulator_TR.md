# Emülatör ekran görüntüleri

[English](ui-emulator.md) · [Türkçe](ui-emulator_TR.md) · [Katkı](../CONTRIBUTING_TR.md)

## Ne işe yarar

İsteğe bağlı emülatör, çalışan Petrel servisinin çizdiği ekranları yakalar. Yerleşimleri incelemek, dokümantasyonu yenilemek ve görsel hataları özgün boyutlu görsellerle bildirmek için kullanın. Gerçek LCD arayüzünü takip eder; bağımsız yazıcı simülatörü değildir. İsteğe bağlı canlı tarayıcı görüntüleme aşağıda anlatılmıştır. Fiziksel encoderle gezinin, ardından SSH üzerinden görüntü isteyin.

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

Çalışan DWIN emülatörü, isteğe bağlı **canlı tarayıcı görüntüsü** sunar. Mouse tekerleği normal enkoder dönüşünü, **orta tuşa tıklama** kısa enkoder basışını üretir. Gerçek LCD ve enkoder çalışmaya devam eder. Uzaktan görüntüleme diske screenshot dosyası yazmaz.

`~/.config/Petrel/Petrel.env` dosyasında etkinleştir:

```ini
PETREL_REMOTE=1
PETREL_REMOTE_HOST=tailscale
PETREL_REMOTE_PORT=8088
```

`PETREL_REMOTE_HOST=tailscale` zaten **varsayılan** değerdir; dosyaya yazmak zorunlu değildir. Petrel açılırken `tailscale ip -4` komutuyla Pi'nin Tailscale IPv4 adresini alır, `100.64.0.0/10` aralığını doğrular ve yalnızca **bu adreste** dinlemeye başlar; localhost, yerel LAN veya tüm ağ arayüzlerinde dinlemez. Tailscale erişilemiyorsa Remote Display açılmaz, ancak fiziksel LCD çalışmayı sürdürür. **SSH tüneli ve Tailscale Serve gerekmez.**

Özelliği içeren sürümü yükledikten sonra yazıcı güvenli şekilde boşta iken Petrel'i yeniden başlat:

```bash
sudo systemctl restart Petrel.service
```

Pi'nin Tailscale IP'sini öğren:

```bash
tailscale ip -4
```

Aynı ve erişim izni olan tailnet'e bağlı bilgisayar/telefondaki tarayıcıdan `http://<PI_TAILSCALE_IP>:8088` adresini aç. Tailscale bu HTTP trafiğini şifreli özel ağı üzerinden taşır; hangi cihazların ulaşabileceği tailnet izinleriyle belirlenir. Bu sunucuda **ayrıca uygulama parolası yoktur** ve yazıcıyı kontrol edebilir: erişimi Tailscale ACL/grant kurallarıyla kısıtla, router üzerinde 8088 yönlendirmesi yapma ve Tailscale Funnel ile internete yayınlama. Uygulama tarayıcılar arası istek riskine karşı Host ve Origin alanlarında tam Tailscale IP kontrolü yapar. Tailscale IP değişirse yeniden bağlanmak için Petrel'i yeniden başlat.

Özellikle **yalnız localhost** istenirse `PETREL_REMOTE_HOST=127.0.0.1` yazıp yeniden başlatılabilir. `0.0.0.0` dahil tüm arayüzlere veya LAN'a bağlanma bilerek desteklenmez. Port gerekirse `PETREL_REMOTE_PORT` ile değiştirilebilir. Tarayıcı açıkken yaklaşık 250 ms'de bir 272×480 JPEG görüntüsü alınır. Mouse olayları Petrel'in normal oturum kontrollü UI kuyruğundan geçer; bağlantı/oturum uygun değilse reddedilir. Orta tuşu basılı tutmak güç uzun basışını simüle **etmez**. Fan, buzzer veya ışık ayarının görüntülenmesi fiziksel olarak çalıştığını kanıtlamaz.

Kapatmak için `PETREL_REMOTE=0` yazıp Petrel'i yeniden başlat. `PETREL_REMOTE=1` mevcut emülatörü otomatik açar; ayrıca `PETREL_EMULATOR=1` gerekmez. Özel Unix screenshot servisi bağımsız çalışmaya devam eder.
