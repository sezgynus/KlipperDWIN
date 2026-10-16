# Maintenance Aşama 8 — Gerçek Raspberry Pi fiziksel kabulü

[English](maintenance-stage8-acceptance.md) · [Çıkış izin profilleri](maintenance-profiles_TR.md) · [LCD kullanım akışı](maintenance-ui_TR.md) · **[Güncel referans yazıcı kullanıcı kabul çizelgesi](maintenance-reference-printer-acceptance_TR.md)**

> **Güncel kabul durumu:** Bu dosyanın aşağıdaki ilk aşama örnekleri tarihî kanıttır. Sonraki sohbetlerde hangi cihazın fiziksel olarak KABUL edildiğini yukarıdaki güncel çizelgeden ve JSON'dan kontrol et.

## Kapsam ve ön şartlar

Aşama 8 geliştirmesi GitHub regresyon testleriyle doğrulanır; ancak sahte verili CI **gerçek aktüasyon, çıkış geri yükleme, buzzer sesi veya LED ışığını kanıtlamaz**. Bunlar gerçek yazıcıda kullanıcı onayı gerektirir. Önceki **Aşama 7** salt-okunur Pi kabulünde altı bilgi kaynağı gözlemlendi; bu Aşama 8'in yerini tutmaz.

Yazıcının standby olduğunu, `virtual_sdcard.is_active=false`, `pause_resume.is_paused=false` durumlarını, kuyrukta baskı ve MMU/probe/kalibrasyon/jog recovery işlemi bulunmadığını doğrula. Test sırasında yazıcının başında bulun. Baskı sürerken veya sıcak parçaların soğutulması için fana güvenilirken aktüatör testi yapma. Case-light/buzzer/generic-fan/LED seçenekleri gerçek donanıma uygun `maintenance-test-profiles.json` dosyasıyla açıkça izin verilene kadar kapalıdır. Part fan F01 ek profile gerek duymaz.

## Master'a birleştirmeden devreye alma

Mevcut `/tmp/petrel-maintenance-acceptance` detached worktree'sini kullan; güncel **imzalı ve CI PASS** `feature/maintenance-test-engine` HEAD'ini fetch edip worktree'yi ona ilerlet. Çalışan `~/Petrel` master dizininde feature checkout yapma. LCD testi için **gerçek Petrel.service**, önceki Aşama 7 A/B testindeki gibi geçici systemd drop-in üzerinden detached feature worktree'nin `WorkingDirectory` ve `ExecStart` değerleriyle başlatılmalı. Geri dönüş trap'i kullan, testten önce servis feature worktree'den açıldığını doğrula. Baskı sırasında servis yeniden başlatılmaz.

## Cihaz üstünde manuel test

1. LCD'den **Maintenance → Self Tests** seç. Yalnız gerçek keşifle doğrulanmış ve açıkça güvenli hedefler listelenebilir. Menüye girmek yazıcıyı hareket ettirmemeli veya çıkışları değiştirmemeli.
2. **F01 fan** veya izin verilmiş opsiyonel çıkışı seç. İhtiyaç anında yapılan kuyruk/başlangıç durumu kontrolünü bekle. BLOCKED görünüyorsa güvenlik denetimini atlatma.
3. Varsayılan **Cancel** seçeneğinden **Run short pulse** seçeneğine enkoderle git ve üç saniyelik süre içinde basarak açıkça onayla. Derlenen tek kısa script uyarımdan sonra başlangıç değerine dönüşü amaçlar.
4. Backend'in komut sonrası GET ile geri dönüşü doğrulamasını bekle. Komutun kuyruğa alınması geri yüklemenin gerçekleştiğini kanıtlamaz. INCONCLUSIVE çıkarsa yeni testten önce fiziksel çıkışı ve Klipper durumunu kontrol et.
5. UI açık kullanıcı gözlemi ister. Ancak kısa fiziksel tepkiyi gördüysen/duyduysan **ve** backend başlangıç değerini doğruladıysa **Yes, observed** seç. Sonuç `PASSED_USER` (insan gözlemi) olur; otomatik PASS veya ölçülmüş RPM değildir. Aksi hâlde **Not observed** (`FAILED_USER`) seç.
6. Gerçekten takılı güvenli cihazlar için ayrı ayrı tekrarla. Her testten sonra fan hızı, LED rengi ve kullanıcı tarafından `visual` olarak tanımlanmış çıkışların değerlerinin başlangıca döndüğünü kontrol et. İptal, kuyruk/baskı engeli, eksik profil ve disconnect davranışını sahte/denetimli koşullarda doğrula; değerli donanımda uyarım sürerken tehlikeli bağlantı kesintisi oluşturma.

**Diagnostics** menüsünü ayrıca incele. S01/S02/S03/S05/S08/S10 yalnız izinli sayısal/metinsel bilgileri gösterir. Moonraker token'ları veya baskı dosya adları ekranda olmamalıdır.

## Master'a dönüş ve kabul kaydı

Geçici systemd override'ını kaldır, `sudo systemctl daemon-reload` ve `sudo systemctl restart Petrel.service` çalıştır; aktif servisin `ExecStart=/home/sezgynpi/petrel-env/bin/python /home/sezgynpi/Petrel/run.py`, `WorkingDirectory=/home/sezgynpi/Petrel` ve master'ın temiz olduğunu doğrula. Güç/bağlantı problemi veya çözümlenmemiş donanım durumu varsa fiziksel testleri durdurup Pi'yi denetle. Feature imzalı SHA, kullanılan izin profilleri, her cihazın gözlemi, geri yüklenen değer, sonuç ve operatör yanıtını kaydet. Testler gerçek Pi'de yapılıncaya kadar Aşama 8 fiziksel kabulü **BEKLEMEDE** kalır.


## Rol tabanlı profiller (feature dalı)

Güncel genel Maintenance dalında yalnız sürüm-2 `actuators` rol eşleştirmeleri geçerlidir; eski `case_light`/`buzzer_output` alanları izin vermez. S18 cihaz bazlıdır; **gerçek** `pwm_cycle_time <ad>` satırını seç. O03 de sabit case-light adını değil, izinli `output_pin <ad>` nesnesini kullanır. [Profil geçişine](maintenance-profiles_TR.md) bak. Aşağıdaki eski Pi gözlemleri tarihsel tanılama örnekleridir; **kaynak koda gömülü pin veya cihaz adları değildir**.

## F01 saha bulgusu ve sonraki doğrulama

2026-10-16 tarihli Remote Display kabulünde F01 parça soğutma fanı kamerada kısa süre çalışırken yürütücü `INCONCLUSIVE / restore_not_verified` döndürdü. Sonradan bağımsız `/printer/objects/query?fan&webhooks` sorgusu `fan.speed=0.0`, `fan.rpm=null`, `webhooks.state=ready` gösterdi. İlk fiziksel deneme **PASS değildir**; anlık geri yükleme doğrulaması başarısız oldu, sonraki okuma da geçmişteki geri yükleme zamanlamasını kanıtlamaz. Yeni doğrulama penceresi/tekrar okuma yamasının CI sahte testleri vardır; feature worktree güncellendikten sonra **yeni** gerçek Pi kabul testi gereklidir. Tekrar fiziksel testten önce yazıcının boşta ve fanın durmuş olduğunu doğrula.

## S18: saha bulgusu ve bekleyen geri okuma kabulü

Pi'de `configfile.settings['pwm_cycle_time buzzer']` için pin PB13, value=0, shutdown_value=0, scale=1 doğrulandı; ancak `printer.objects.list` nesneyi içermiyor ve `printer.objects.query` durum sunmuyor. Güncellenen S18 izinli akışı yalnız yapılandırmadan keşif ve **insanın ses gözlemi** üzerine kuruludur; `OBSERVED_USER` sonucu doğrulanmış geri yükleme anlamına gelmez. Bu Klipper nesnesinde S18'in telemetriyle geri yükleme kabulü **mümkün değildir**. `buzzer_output='buzzer'` izni, fiziksel buzzer'ın doğru ve yazıcı boşta iken güvenli uyarılabilir olduğundan emin olunduktan sonra kullanılmalıdır. CI sahte testini gerçek donanım kabulü sayma.

## S18 büyük/küçük harfe duyarlı G-code saha bulgusu

2026-10-16 tarihinde S18 listede görünmeye başladı, ancak ilk fiziksel deneme `INCONCLUSIVE / script_failed_or_restore_unknown` ile sonuçlandı: Klipper'ın geçerli mux seçeneği `Buzzer` iken Petrel `PIN=buzzer` üretti. Çıkışın gerçekten uyarıldığı **doğrulanmadı**. İmzalı düzeltme salt-okunur ön kontrolde özgün, büyük/küçük harfe duyarlı bölüm adını çözümler. Yeni ve boşta yazıcı üzerinde kısa sesin **çıkıp ardından kesildiğini** gösteren fiziksel test `OBSERVED_USER` olarak kaydedilene kadar Aşama 8 S18 **BEKLEMEDE** kalır; durum geri okuma doğrulaması iddia edilmez.
