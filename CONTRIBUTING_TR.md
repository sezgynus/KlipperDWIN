# Katkıda bulunma

[English](CONTRIBUTING.md) · [Türkçe](CONTRIBUTING_TR.md) · [Dokümantasyon](docs/README_TR.md)

## Hata bildirme veya özellik önerme

GitHub issue açıp ne denediğinizi, ne beklediğinizi ve ne olduğunu anlatın. KlipperDWIN revizyonunu, Pi/işletim sistemini, ekran modelini, ilgili Klipper/Happy Hare sürümlerini, tekrar üretme adımlarını ve kısa servis günlüğünü ekleyin. Görsel sorunlarda özgün boyutlu ekran görüntüsü ve gerektiğinde fiziksel ekran fotoğrafı paylaşın. Kimlik bilgilerini ve özel ağ bilgilerini kaldırın.

Özellik önerisi kullanıcı akışını ve gereken yazıcı özelliğini anlatmalıdır. Kod, dokümantasyon, çeviri, ikon veya donanım test sonucu ile katkı yapılabilir.

## Değişiklik hazırlama

Güncel `master` üzerinden dal açın; değişikliği odaklı tutun ve problemi, sonuçta oluşan davranışı ve doğrulamayı anlatan pull request açın. Moonraker Update Manager kurulu repoyu temiz tutabilsin diye ayrı geliştirme kopyası kullanın. Makine ayarlarını harici ortam dosyasında tutun.

Kullanıcının gördüğü değişikliklerde ilgili rehberi ve ekran görüntülerini güncelleyin. **İngilizce ve Türkçe belgeler aynı özellik ve adımları kapsamalı**, aynı görselleri/sırayı kullanmalı ve ekrandaki adları korumalıdır. Güncel kullanım rehberlere, geçmiş audit'ler referanslara aittir.

## Geliştirme araçları

| Araç | Ne işe yarar | Başlangıç |
|---|---|---|
| İsteğe bağlı framebuffer emülatörü | Görsel inceleme, dokümantasyon ve hata bildirimi için çalışan LCD arayüzünü yakalar | [Emülatör rehberi](docs/ui-emulator_TR.md) |
| Regresyon testleri | Yazıcıya bağlanmadan veya hareket ettirmeden değişikliği kontrol eder | [Test rehberi](tests/README_TR.md) |
| JPEG ikon paketleyici | İkon ekler ve yönetilen kütüphaneyi dışa aktarır | [İkon kaynak rehberi](assets/icons/README_TR.md) |
| Servis günlükleri | Açılış, bağlantı ve işlem hatalarını incelemeyi sağlar | [Sorun giderme](docs/installation_TR.md#sorun-giderme) |

## Çalıştırma ve doğrulama

Kurulu Pi'de mevcut uygulama ortamı çalışma bağımlılıklarını içerir. Testleri geliştirme kopyasından çalıştırın:

```bash
~/klipperdwin-env/bin/python -m unittest discover -s tests -v
~/klipperdwin-env/bin/python -m compileall -q .
```

Uygulamayı manuel denerken UART ve encoderi tek süreç kullansın diye önce kurulu servisi durdurun. Kendi bağlantı/pin değerlerinizi verin; `run.py` doğrudan çalıştırıldığında servisin ortam dosyasını okumaz ve yalın UART/düğme varsayılanları kurulumdan farklıdır:

```bash
sudo systemctl stop KlipperDWIN.service
cd ~/KlipperDWIN
~/klipperdwin-env/bin/python run.py \
  --serial-port /dev/ttyS0 \
  --encoder-pins 21 19 \
  --button-pin 20 \
  --moonraker-url http://127.0.0.1:7125
```

Manuel süreçten çıktıktan sonra `sudo systemctl start KlipperDWIN.service` ile kurulu servisi başlatın. Seçenekler için `run.py --help` kullanın; CLI değerleri ortam değerlerinden önceliklidir. Hareket, kalibrasyon ve MMU değişikliklerini otomatik testlere ek olarak uygun donanımda deneyin.

## Ekran görüntüleri ve dokümantasyon

Ekranı [emülatörle](docs/ui-emulator_TR.md) yakalayın. Açıklayıcı adlarla `docs/assets/screens/` içine kaydedin; aynı ekran/durumu temsil ediyorsa mevcut görseli değiştirin. Özgün **272×480 PNG** korunsun; büyütmeyin, kırpmayın veya JPEG'e çevirmeyin. Markdown'da tutarlı gösterim genişliği ve her dilde anlamlı alt metin kullanın.

PR açmadan önce yerel bağlantıları, bölüm bağlantılarını, görsel yollarını, çeviri çiftlerini ve kullanıcı komutlarını kontrol edin. Davranış değiştirmeyen dokümantasyon düzenlemelerinde yazıcı regresyon testleri gerekmez.
