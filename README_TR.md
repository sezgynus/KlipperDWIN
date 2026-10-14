<p align="center">
  <img src="assets/petrel-readme.png" width="600" alt="Petrel — yazıcı üzerindeki yerel arayüz">
</p>

**Desteklenen stok DWIN ekranları için Moonraker ile çalışan hafif yazıcı arayüzü.**

Klipper'a geçtikten sonra uyumlu Ender 3 V2 ekranını yeniden kullanın: yazıcının enkoderinden dosya seçin, baskıyı ayarlayın, tablayı hazırlayın ve filament bilgilerini inceleyin.

[English](README.md) · [Türkçe](README_TR.md) · **[Petrel kurulumu](docs/installation_TR.md)** · [Ekran uyumluluğu](docs/lcd-assets_TR.md)

<p align="center">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776ab?logo=python&amp;logoColor=white">
  <img alt="Klipper / Moonraker" src="https://img.shields.io/badge/Klipper-Moonraker-7d3cff">
  <a href="LICENSE"><img alt="GPL-3.0" src="https://img.shields.io/badge/License-GPL--3.0-blue"></a>
</p>

<p align="center">
  <a href="docs/assets/screens/home.png"><img src="docs/assets/screens/framed/home.png" width="220" alt="İsteğe bağlı MMU ile Petrel Home"></a>
  <a href="docs/assets/screens/printing.png"><img src="docs/assets/screens/framed/printing.png" width="220" alt="Baskı ilerlemesi ve enkoder kontrolleri"></a>
  <a href="docs/assets/screens/tune.png"><img src="docs/assets/screens/framed/tune.png" width="220" alt="Çalışma anındaki Tune ayarları"></a>
</p>

**Tam boyut aç:** [Home](docs/assets/screens/home.png) · [Print](docs/assets/screens/printing.png) · [Tune](docs/assets/screens/tune.png).

*Gerçek UI/driver kodunun örnek verilerle üretilmiş emülatör çıktısıdır; fotoğraf veya fiziksel ölçüm değildir. [Ekranları inceleyin](docs/screenshots_TR.md).*

## Neden Petrel?

Desteklenen stok ekran, yazıcı Klipper'a geçtiğinde önceki işlevini kaybedebilir. Petrel günlük kontrolleri yeniden yazıcının yanına getirir; baskıyı kontrol etmek veya sıcaklığı değiştirmek için her seferinde telefon ya da tarayıcı açmanız gerekmez. Desteklenen paneli kullanmaya devam edersiniz; Linux SBC, bağlantı kabloları ve çalışan Klipper/Moonraker kurulumu yine gereklidir.

Arayüz mevcut enkoderi ve panelin native çizim komutlarını kullanır. Host üzerinde Python servisi çalışır; yazıcı durumu Moonraker WebSocket aboneliğinden gelir. “Hafif” bu mimariyi anlatır; proje karşılaştırmalı CPU, RAM veya gecikme ölçümleri yayımlamaz. KlipperScreen dokunmatik ekranla farklı bir donanım/arayüz seçeneği sunar; ekipmanınıza ve iş akışınıza uygun arayüzü seçin.

## Günlük kontroller ve isteğe bağlı entegrasyonlar

| İşlem | LCD'de sunulanlar |
|---|---|
| Baskı seçme | İç içe klasörler, Mainsail sıralaması, model önizlemesi, tahmini süre ve varsa dilimleyici filament/tool bilgileri |
| Baskı yönetme | İlerleme/süre, isteğe bağlı katman bilgisi, doğrudan Pause/Resume, onaylı Stop ve tamamlanınca Close |
| Tune | Speed/Flow, fan ve sıcaklıklar, oturumluk Z offset, SCV/minimum cruise ratio, destekleniyorsa PA/smoothing ve firmware retraction |
| Hazırlık ve kalibrasyon | Homing, motorlar, XYZ/ekstrüder hareketi, Live jog, preset/soğutma, bed mesh, dört köşe vida ayarı ve probe-offset kalibrasyonu |
| Happy Hare MMU | Canlı filament yolu/purge, gate'ler, yükleme/boşaltma, bypass, tool map, EndlessSpool, kullanıcı seçimiyle kurtarma, desteklenen LED'ler ve çoklu üniteler |
| Spoolman | Makara ID'leri ve gate malzeme/rengi; Happy Hare/Spoolman entegrasyonu sağlıyorsa kalan yüzde |
| Ekran ve sistem | Parlaklık/karartma, buzzer/tonlar, ağ/host/MCU/yazılım durumu, QR bağlantısı ve yazıcı boşta iken Petrel güncellemeleri |
| Işık ve güç | Yapılandırılmış PWM kasa ışığı ve Moonraker güç cihazı; onaylı enkoder basılı tutma ve aktif baskıda kapatma engeli |
| After Job | Üç isteğe bağlı politika switchi; yalnız pinleri değiştirir, iş sonundaki eylemleri makrolarınız yapar |

MMU ve Spoolman isteğe bağlıdır. Menüler algılanan yapılandırmaya ve geçerli duruma bağlıdır; ekran etiketleri İngilizce kalır. Maintenance şu anda yalnız Back içerir. [Print/Tune alanlarının tam tablosuna](docs/print-controls_TR.md) bakın.

## Uyumluluk ve gereksinimler

- Uyumlu 4.3 inç Ender 3 V2 paneli dahil **272×480 dikey DWIN T5UIC1**. Diğer DWIN modellerinin veya DACAI/TJC'nin çalıştığı varsayılmaz.
- UART/GPIO bulunan Raspberry Pi veya uyumlu Linux SBC ve **Python 3.11+**.
- Çalışan **Klipper ve Moonraker**, yetkili ağ erişimi, çapraz TX/RX bağlantısı ve yapılandırılmış enkoder pinleri.
- Panelin SD güncelleme yöntemiyle bir kez kurulan paket LCD fontu; açılış görseli ve ikonlar UART üzerinden otomatik eşitlenir.

Başlamadan önce [ekran/kaynaklar](docs/lcd-assets_TR.md) ve [bağlantıları](docs/installation_TR.md#bağlantı-ve-seri-port-hazırlığı) kontrol edin. Desteklenen mevcut panel yeni ekran alma ihtiyacını azaltır; SBC/kablo gereksinimlerini ortadan kaldırmaz.

## Hızlı başlangıç

Bu belgeler, Petrel'in `master` ile birleşecek `feature/graphite-theme` dalındaki güncel arayüz restorasyonu geliştirmesini anlatır. Buradaki ekranları elde etmek için bu dalı kullanın:

```bash
cd ~
git clone --branch feature/graphite-theme https://github.com/sezgynus/Petrel.git
cd ~/Petrel
./install.sh
```

Installer bağımlılıkları, `Petrel.service` servisini, harici ayarları ve Moonraker Update Manager kaydını hazırlar. [LCD fontu ve ilk açılış kontrollerini](docs/installation_TR.md#lcd-kaynakları-ve-ilk-açılış) tamamlayın. Update Manager şu anda `master` izler; geliştirme kopyasını güncellemeden önce [güncelleme rehberini](docs/installation_TR.md#güncelleme) okuyun. Mevcut kurulumların ayarları [geçişte](docs/installation_TR.md#güncelleme) korunur.

Bağlantı/enkoder/güç ayarlarını daha sonra değiştirmek için `~/Petrel` içinde `./configure.sh` çalıştırın. Gezinmek için çevirin, seçmek için basın; sayısal değerlerde çevirip yeniden basarak onaylayın. Tune düzenleyicisi **Apply** kullanır; bazı sayfalarda ayrıca **Save** gerekir. **Back** geri döner; Home sayfaları arasında ilerlemek için çevirmeye devam edin.

## Doğru rehberi bulun

| Rehber | Öğrenecekleriniz |
|---|---|
| [Kurulum ve yapılandırma](docs/installation_TR.md) | Bağlantılar, LCD fontu, ilk açılış, ayarlar, güncellemeler ve sorun giderme |
| [Günlük kullanım](docs/user-guide_TR.md) | Dashboard birimleri, dosya seçimi, hareket, ısıtma, kalibrasyon, Display, Info ve güç |
| [Print ve Tune](docs/print-controls_TR.md) | Olası 17 alan, komut sonuçları, isteğe bağlı iş switchleri ve MMU hata akışı |
| [MMU ve filament](docs/mmu-guide_TR.md) | Gate/makara, eşleme, EndlessSpool, bypass, durum bildirme ve kurtarma |
| [Ekran galerisi](docs/screenshots_TR.md) | Özgün panel PNG bağlantılarıyla çerçeveli önizlemeler |
| [Dokümantasyon dizini](docs/README_TR.md) | Kullanıcı/katkı rotaları ve isteğe bağlı tarihsel kaynaklar |

Çalışma anındaki ayarlar kalıcı Klipper/probe yapılandırmasının yerini almaz. Vida ayarı prob ve yapılandırılmış dört köşe vidası gerektirir. Mesh görüntülemek onu etkinleştirmez; kaydetmek Klipper'ı yeniden başlatır, ölçümü açıkça durdurmak shutdown yapar. MMU kalibrasyonu/özel LED efektleri web arayüzünde kalır. Belirsiz bir komuttan sonra tekrar denemeden önce gerçek yazıcı durumunu kontrol edin.

## Mimari ve geliştirme

Petrel, Moonraker aboneliğinden gelen durumla enkoder girdisini T5UIC1 UART çizim komutlarına dönüştürür. Önizlemeler panel SRAM'ini kullanır; yönetilen açılış/ikon kaynakları Picture Flash ve değişmeyen blokları tekrar yüklemeyi önleyen parmak izleri kullanır. Kalıcı ekran/buzzer kayıtları ayrı Data Flash içindedir.

Bağlantı kurulurken Moonraker nesne listesi ve yapılandırma okunur; yeniden bağlantıda tekrarlanır. Capability/durum modelleri görünen kontrolleri ve sınırları belirler. Bu koşullu menü görünürlüğüdür; dinamik modül yükleme değildir. Yeni bir MMU protokolü, algılamanın yanında durum eşlemesi, komut uyarlaması ve testler gerektirir.

[Katkı](CONTRIBUTING_TR.md), [testler](tests/README_TR.md), [PNG/GIF yeniden üretimi](docs/ui-emulator_TR.md#dokümantasyon-ekranlarını-çevrimdışı-üretme) ve [ikon kaynakları](assets/icons/README_TR.md) ile başlayın. Fiziksel panel çalışmaları için isteğe bağlı [protokol referansını](docs/t5uic1-reference.md) kullanın.

## Katkılar ve lisans

Proje [odwdinc/DWIN_T5UIC1_LCD](https://github.com/odwdinc/DWIN_T5UIC1_LCD) ve [bustedlogic/DWIN_T5UIC1_LCD](https://github.com/bustedlogic/DWIN_T5UIC1_LCD) çalışmalarından gelişti. Özgün telif bildirimleri ve Git geçmişi korunur.

Entegrasyonlarda [Klipper](https://github.com/Klipper3d/klipper), [Moonraker](https://github.com/Arksine/moonraker), [Mainsail](https://github.com/mainsail-crew/mainsail), [Happy Hare](https://github.com/moggieuk/Happy-Hare) ve [Spoolman](https://github.com/Donkie/Spoolman) kullanılır.

**GNU GPL v3.0** lisanslıdır; [LICENSE](LICENSE) dosyasına bakın.
