# Yönetilen LCD ikonları

[English](README.md) · [Türkçe](README_TR.md)

Baseline **4:2:0 JPEG** dosyalarını buraya ekleyin veya mevcut olanları değiştirin. Dosya adı ikon ID'siyle başlamalı: `092.jpg`, `092-about.jpg` veya `092_about.jpeg`. ID aralığı 0–255'tir; her ID yalnız bir dosyada kullanılabilir. Mevcut ID'lerin anlamı korunur. ID ve içerik aynı kalırken dosya adını değiştirmek yükleme başlatmaz. Yeni görsel kütüphaneye girer; ID'nin arayüzde nerede gösterileceğini UI kodu seçer.

JPEG'ler boyutlandırılmadan ve yeniden sıkıştırılmadan korunur. Progressive JPEG, diğer renk örnekleme biçimleri, yinelenen ID ve 32767 bayttan büyük görseller reddedilir. Kütüphane Picture Flash 3–15 slotlarına sığmalıdır; resim 0 Petrel açılış görselidir, resim 1 ortak UI görsel sayfasıdır ve resim 2 kullanılmaz.

Uygulama güncellemesinden sonraki ilk LCD bağlantısında bu klasörden kütüphane oluşturulur. Paketleyici büyük ikonları önce yerleştirir ve küçük ikonlarla kalan boşlukları doldurur. ID sırası fiziksel yerleşimden bağımsızdır. Her bloğun son baytı ayrılır ve UART yazımına dahil edilmez. Hiçbir JPEG blok sınırını geçmez.

Yalnız değişen bloklar yüklenir; tablo bloğu en son yazılır. Paneldeki kayıt tamamlanan blokları saklar; sonraki açılış eksik yüklemeyi tamamlar. Değişmeyen kütüphanede Flash yazılmaz. Başarısız Picture Flash denemesi aynı süreçte tekrarlanmaz. Yükleme ilerlemesi ve hatalar loglarda yer alır.

Çalışma sırasında kullanılan paketin aynısını dışa aktarın:

```bash
python tools/pack_icon_library.py assets/icons /tmp/3.ICO --library 3
```

Emülatör de bu JPEG kaynaklarını kullanır. `assets/emulator/3.ICO` referans çıktıdır; otomatik güncellemenin kaynağı değildir.

Özel UI ikonları 100–109 ve 124 ID'lerini kullanır. MMU 100/101, Display 108/109 ID'leriyle seçili olmayan/seçili 110×100 ana menü ikonlarını kullanır; boyutlar mevcut ana menü yerleşimine uyar; normal ve seçili Graphite yüzeyleri farklıdır. Boş makara 124 ID’sini kullanır. Metal makara yan parçaları 1–7 genişlikleri için 110–123 ID'lerini kullanır; dar alanlarda ayrı tam makara görselleri gerekmez. Sembolik eşleştirme `lcd_resources.py` içindedir. Tüm UI ikonları doğrudan kütüphane 3'den çizilir.

Panel kaynaklarını yeniden yüklediğinizde, kayıt eski kurulumu tarif ediyor olabileceğinden zorla yeniden yükleyin:

```bash
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/reload_icons.py
sudo systemctl start Petrel.service
```

Yazma onayları ve kayıt geri okuması doğrulanır; Picture Flash'ın kendisi geri okunmaz. Yeni ikon yerleşimini fiziksel ekranda kontrol edin.

## Graphite

Graphite; ışık, parlaklık, ses ayarları, hareket parametreleri, kalibrasyon ve profiller için 210–234 ID’lerini ekler. Düzenlenebilir SVG kaynakları `assets/icon-source` içindedir; JPEG üretmek için `python tools/render_icon_sources.py` çalıştırın (geliştirme bağımlılığı: CairoSVG). Siyah JPEG zemini panelin şeffaf/enhanced ikon modu ile filtrelenir; menü ve dashboard yüzeyleri korunur. İkon paketi 3 numaralı slotta başlar, 3–15 slotlarını kullanabilir; 512 baytlık metadata kaydı Data Flash `0x0200–0x03FF` aralığındadır.

## Print butonları, switchler ve fan görselleri

Print butonları yuvarlatılmış yüzeyi, seçim çerçevesini ve Lucide simgesini tek JPEG içinde taşır; etiketler panelin **0 numaralı fontuyla** native metin olarak çizilir. Normal dar butonlar **243–247**, seçili karşılıkları **125–129** (78×36); tamamlanan baskının Tune/Close çiftleri **130–133** (119×36) ID'lerini kullanır. AFTER JOB switchleri **248/249** (27×12) kullanır. Normal/seçili siluetleri aynı tutun: üretici aynı nötr opak kenarı taşıyan keskin yuvarlak maske kullanır; böylece filtrelenen JPEG kenarlarında önceki durumun pikselleri kalmaz.

Fan kareleri **235–242** nötr gri tonlarla üretilir; siyah saydamlık zeminindeki çınlamayı önlemek için kodlamadan önce 24 altı parlaklık temizlenir. Fan ve tam buton JPEG'leri **kalite 100**, baseline **4:2:0** kullanır. Diğer üretilen ikonlar kalite 94 kullanır. JPEG'i tekrar sıkıştırmak yerine SVG'den üretin. Lucide kaynak lisansı: [Lucide lisansı](../icon-source/Lucide-LICENSE.txt).

## Paket boyutu ve ayrılan alan

Mevcut referans paket **9×32 KiB = 288 KiB**, yani **3–11** slotlarını kullanır. Ayrılan üst sınır **13×32 KiB = 416 KiB**, yani **3–15** slotlarıdır; **12–15** büyüme için kullanılabilir. Bu ayrılmış blok alanıdır; birebir JPEG veri bütçesi değildir: dizin, yerleşim boşlukları ve blokların ayrılmış son baytları da alan tüketir. Picture Flash, **0x0200–0x03FF adresindeki 512 baytlık Data Flash metadata kaydından** ayrıdır. Export sırasında `--library 3` verin; aracın eski varsayılanı 7'dir ve kullanılabilir slot sayısı farklıdır.

## JPEG uyumluluk kuralı

Yönetilen tüm ikonlar baseline RGB/YCbCr JPEG ve **4:2:0** örnekleme kullanmalıdır (`Pillow: subsampling=2`). `tools/render_icon_sources.py` ile doğrudan SVG’den üretin; JPEG’leri tekrar tekrar sıkıştırmayın. Fiziksel T5UIC1 testinde 4:4:4, hem Flash hem baytları geri okunarak doğrulanmış SRAM üzerinden seçili ana menü kartlarını ve homing görselini bozdu; 4:2:0 düzgün çizildi. Temiz emülatör görüntüsü panelin JPEG çözücüsünü doğrulamaz. Kaynak yükleyici diğer örnekleme biçimlerini panele erişmeden reddeder; CI tüm ikonların biçimini ve ICO’nun kaynaklarla eşleşmesini kontrol eder. Görsel güncellemelerden sonra seçili/seçili olmayan ana menü kartlarını, homing’i, küçük menü/durum ikonlarını ve animasyonu fiziksel panelde kontrol edin.
