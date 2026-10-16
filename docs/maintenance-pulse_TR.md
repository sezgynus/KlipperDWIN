# Maintenance Aşama 8B — süre sınırlı aktüatör komutlarının oluşturulması

[English](maintenance-pulse.md)

Bu katman **yalnız saf komut üreticisidir**: hiçbir metot komut göndermez, test başlatmaz, fiziksel PASS iddiasında bulunmaz veya güvenliği atlatmaz. Yalnız tam eşleşen USER yönlendirmeli keşif kayıtları değişmez `PulseProgram` oluşturabilir. G-code; izin listeli tek uyarım, 150–950 ms `G4` beklemesi ve **tek sınırlı script** içinde başlangıç durumuna dönme komutundan oluşur. Donanımın orijinal firmware durumu yoksa veya güvenilir değilse başlatılamaz. Harici istemciler ya da Klipper yeniden başlatması script'i kesebilir; sonraki executor geri yüklenen çıkışı ayrıca doğrulamadan geri yükleme gözlendi diyemez.

Donanım profilleri: F01 part fan M106 kullanır, RPM değil önceki komutlanan PWM'i geri yükler; F04 fan_generic yalnız tam SET_FAN_SPEED kullanır, template ve güvensiz isimleri reddeder; O03 açıkça `visual` rolü atanmış, ölçeği 1, başlangıç değeri canlı okunan ve ham pin kimliği doğrulanan her `output_pin` PWM içindir; O04 tüm color_data bilgisi bilinen tek LED elemanını SET_LED ile geri yükler, çoklu piksel şeritlerini çalıştırmaz; S18 her bir kayıtlı `audible` rolündeki `pwm_cycle_time` için ayrı uygulanır; varsayılan ve shutdown değerinin 0 olması canlı OFF telemetrisi değildir. Desteklenmeyen donanım engellenir. Klipper G-code sözdizimi resmî [G-Codes](https://www.klipper3d.org/G-Codes.html) belgesinde açıklanır.

Sonraki executor, yazıcıyı boşta tutmalı, Moonraker job queue ve Petrel işlemlerini doğrulamalı, komut gönderimini korumalı, menüye girişte otomatik test başlatmamalı, sonrasında hedefi yeniden okumalı, kullanıcının fiziksel EVET/HAYIR gözlemini status değerlerinden ayırmalı ve doğrulanamayan durumda INCONCLUSIVE sonucunu korumalıdır. Tüm testler yalnız GitHub CI'da yürütülür.

## S18 geri okuma sınırı

Açık izinle etkinleştirilen `pwm_cycle_time` buzzer için Klipper durum geri bildirimi yoktur. Sınırlı script önce KAPALI komutu gönderir, 50 ms bekler, 150 ms ses üretir ve yeniden KAPALI komutu gönderir. Toplam 200 ms'lik program geri yüklemeyi **dener**, ancak fiziksel gerçekleştiğini kanıtlamaz; `restored()` fonksiyonu uydurma durum değeri verilse bile S18'i telemetriyle doğrulanmış saymaz. Yalnız kullanıcı izni verilmiş, efektif yapılandırmada varsayılanı KAPALI olan tam çıkış kabul edilir.

S18/O03 SET_PIN derleyicileri Klipper'ın ham yapılandırmasından ayrı olarak doğrulanan, özgün harf biçimini koruyan `pin_command_name` ister. Eksik veya harflerden bağımsız olarak farklı adları reddeder ve bütün `SET_PIN PIN=` komutlarında yalnız bu doğrulanmış yazılışı kullanır.

## O04 LED zincirleri: otomatik yetenek keşfi, güvenli test

O04 donanımdan bağımsızdır. Klipper'ın başka bir denetleyici tarafından yönetilmeyen \`led\`, \`neopixel\`, \`dotstar\` ve \`pca9632\` zincirlerinde 1–32 aynı tip RGB/RGBW piksel, açık \`led\` rolü izni, kullanıcı onayı, indeksli renk uyarımı ve piksel başına önceki renklerin iki geri okumayla kontrolü korunur. Yazılımsal durum fiziksel ışık çıkışının kanıtı değildir; \`PASSED_USER\` için olumlu kullanıcı gözlemi her zaman zorunludur.

Happy Hare için Petrel, **sabit MMU adı, pin veya gate sayısı kullanmadan** efektif \`[mmu_leds <birim>]\` ayarlarını ve gerçek Klipper nesnelerini inceler. Fiziksel zincir \`exit_leds\`, \`entry_leds\`, \`status_leds\`, \`logo_leds\` segmentlerine bölünebilir; ayrı indeks aralıkları ve farklı MMU birimleri desteklenir. Her segmentin fiziksel indeksleri kesin, çakışmasız ve sınırlandırılmış olmalıdır. Güvenilir Happy Hare LED zincirleri, yazıcıya özel LED profili gerekmeksizin otomatik olarak **kullanıcı onaylı test adayı** olarak keşfedilir. Keşif asla komut göndermez veya otomatik PASS üretmez.

İlgili her birime, Happy Hare'nin **kendi LED denetleyicisi** üzerinden \`MMU_SET_LED UNIT=<keşfedilen-birim> [SEGMENT_EFFECT=(r,g,b)...] DURATION=1 FADETIME=0\` komutu gönderilir. Renk, kapsanan LED'lerin alınmış başlangıç renklerinden farklı ve düşük parlaklıklı seçilir. Bir birimin birden fazla segmenti tek komutta belirtilebilir; farklı birimler ayrı komutlarla yönetilir. Happy Hare zincirine doğrudan \`SET_LED\` yazılmaz ve LED yöneticisi devre dışı bırakılmaz. Happy Hare'nin bir saniyelik zamanlayıcısından sonra her ilgili \`mmu_leds\` nesnesinin önceki \`enabled\` ve \`animation\` değerleri iki geri okumayla karşılaştırılır. Bu yalnızca **kontrol politikasını** doğrular; animasyonlu renklerin birebir geri geldiğini veya fiziksel ışığın çalıştığını kanıtlamaz. Görsel kullanıcı onayıyla sonuç \`OBSERVED_USER\`, **\`restore_verified=False\`** olur.

Bütün fiziksel testlerde çift açık onay, güncel yazıcı/kuyruk/işlem güvenlik denetimleri ve sınırlı komutlar korunur. Devre dışı LED denetimi, meşgul MMU, eksik/çelişkili durum kanıtı, yinelenen veya sınır dışı LED indeksleri, bir segmentte birden fazla fiziksel zincir, desteklenmeyen isimler ve aynı fiziksel zincire bağımsız efekt sahipliği ön kontrolde reddedilir. Fiziksel zincirin yalnız bir bölümü eşlenmişse ancak **değiştirilecek her pikselin sahibi kesin olarak belirlenmişse** o bölüm test edilir; diğer piksellere bilerek müdahale edilmez. Bilinmeyen eklentilerin LED kontrolü tahmin edilmez. CI taklit testi, fiziksel kabul değildir.

### Happy Hare sayısal UNIT uyumluluğu

[mmu_leds AD] bölümündeki ek, G-code UNIT indeksi olmak zorunda değil; birim ADIDIR. Bazı Happy Hare sürümleri yalnızca sayısal UNIT argümanı kabul eder. Petrel sayısal indeksi, Happy Hare'nin birimleri oluştururken kullandığı yetkili [mmu_machine] units sıralamasından çözer. Birim adındaki rakamdan indeks çıkarmaz ve ilk birimin adını unit0 varsaymaz. Eksik, yinelenmiş veya tutarsız eşleme G-code gönderilmeden testi engeller. Böylece gerçek sistemlerde görülen "unable to parse unit0" hatası giderilir.

### Happy Hare birim kimliği ile görünen adın ayrılması

Yüklü Happy Hare `mmu_machine` nesnesi, etkin `configfile.settings.mmu_machine.units` alanı bulunmasa da `num_units` ve ardışık `unit_N` kayıtlarını verebilir. Bazı sürümlerde canlı `unit_N.name`, `[mmu_leds AD]` bölümündeki gerçek birim kimliği değil, **kullanıcıya gösterilen etikettir**. Bu iki adın eşleşmesi gerekmez. Petrel görünen adı G-code içine yazmaz; bölüm adında geçen rakamdan da indeks tahmin etmez.

Sayısal `UNIT` indeksi iki sınırlı ve salt okunur kanıttan biriyle çözülür: (a) etkin `[mmu_machine] units` listesinin doğrulanmış sırası, mevcutsa canlı birim sayısı ve karşılaştırılabilir gerçek kimliklerle tutarlı olmalıdır; veya (b) **tam olarak tek bir** canlı MMU birimi, seçili zinciri yöneten **tam olarak tek bir** yapılandırılmış MMU LED denetleyicisi ve geçerli `unit_0` kaydı bulunmalıdır. İkinci durumda kullanıcıya görünen addan bağımsız olarak `UNIT=0` kesinleşir; yazıcıya özel istisna eklenmez. Birden fazla MMU birimi bulunup gerçek sıralama doğrulanamıyorsa görünen adlar yeterli sayılmaz ve O04 engellenir.

Keşif abone olunmuş canlı durumla, fiziksel ön kontrol ise yeniden sorgulanan güncel durumla aynı kanıtı doğrular. Yazıcı/kuyruk güvenlik denetimi, geçici Happy Hare efekti ve zorunlu kullanıcı gözlemi korunur. Belirsiz veya çelişen birim/denetleyici sayısında G-code gönderilmez.
