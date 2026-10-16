# Maintenance Aşama 8C — güvenlik kontrollü fiziksel pulse yürütücüsü

[English](maintenance-physical.md)

`MaintenancePulseController` yalnız kullanıcı isteğiyle çalışan backend durum makinesidir. Desteklenen fiziksel işlemler sadece Aşama 8B'nin hazırladığı `PulseProgram` komutlarıdır; en fazla 950 ms uyarım ve aynı script içinde başlangıç değerine dönüş içerir. Petrel'in mevcut read worker'ını, Moonraker HTTP istemcisini, `postREST` komut kuyruğunu, değişmez discovery'yi, doğrulanmış job queue/operasyon güvenliğini ve açık `GuidedConsentGate` kullanır.

İki ayrı UI eylemi zorunludur: önce keşfedilen testi seçmek (salt okunur kuyruk + başlangıç değeri sorgulanır), ardından ön kontrol bittikten sonra **üç saniye içinde** açıkça onaylamak. Menü girişi veya keşif asla komut göndermez. Dispatch-time guard Klipper epoch/config değişimini, baskı/pause/manual-probe/MMU işlemlerini, eskimiş kuyruk kanıtını ve bilinmeyen durumu reddeder. `postREST` kısa G-code'u kuyruğa alır; tamamlandıktan sonra ayrıca yapılan GET başlangıç değerine dönüşü doğrulamalıdır. Ancak bundan sonra kullanıcıya fiziksel gözlemi sorulur ve **yalnız açık EVET** `PASSED_USER` üretir. Otomatik PASS veya RPM uydurulmaz.

ÖNEMLİ: Moonraker timeout/bağlantı kopması, script geri alma içeriyor olsa bile komutun çalışıp çalışmadığını belirsiz bırakabilir. Controller `INCONCLUSIVE` döndürür; zamanı aşmış komutu tekrar göndermez. İptal/timeout sonrasında belirsiz komut çalışmaya devam edebilir. Kullanıcı donanımı kontrol etmelidir; yerel rezervasyon harici Moonraker istemcilerini kilitlemez. Bu tasarım hard real-time fail-safe garantisi vermez. Özellikle orijinal çıkış değeri doğrulanamazsa, kuyruk bilinmiyorsa, template aktifse veya son GET başlangıçla uyuşmuyorsa **başarı engellenir**.

LCD arayüzü ve gerçek Pi aktüatör kabulü ayrı doğrulanmalıdır; CI taklitleri fiziksel donanımın çalıştığını kanıtlamaz.

## Gecikmeli Moonraker geri yükleme telemetrisi (Aşama 8 F01 kabulü)

Gerçek Raspberry Pi kabulünde F01 fan kısa süre çalışmasına rağmen `INCONCLUSIVE / restore_not_verified` görüldü; sonradan yapılan salt-okunur Moonraker sorgusunda `fan.speed=0.0` okundu. Önceki tek GET, G-code yürütmesi/telemetri güncellemesiyle yarışabilir; ancak bu gözlem gecikmenin tam nerede oluştuğunu tek başına kanıtlamaz. Yeni akış, G-code gönderiminden itibaren en az pulse süresi ve ek payı, HTTP tamamlanmasından itibaren de en az 250 ms bekler. Ardından **en az 300 ms aralıkla üst üste iki eşleşen durum GET'i** ister; doğrulama penceresi **altı saniyeyle sınırlıdır**. Bütün okumalar mevcut bounded worker ve UI tick ile yapılır; sleep, yeni worker thread'i veya tekrar G-code gönderimi yoktur.

Ara değer uyuşmazlığı veya geçici okuma hatası düzelebilir; kalıcı uyuşmazlık `restore_value_mismatch`, başarısız okumalar `restore_readback_unavailable`, yeterli kararlı eşleşme olmaması `restore_not_stable`, yazıcı epoch/yapılandırma değişimi `state_changed_during_restore_check` üretir. Zaman aşımı veya belirsizlik hâlinde sonuç **INCONCLUSIVE** kalır; otomatik PASS verilmez. İki eşleşen örnek yalnız bildirilen durumu doğrular, ileride yürütülebilecek kuyruktaki G-code için mutlak güvence değildir; fiziksel gözlem ve kullanıcının açık EVET onayı yine zorunludur. Belirsiz testten sonra çıkışı kontrol etmeden fiziksel pulse tekrarlama.

## Yalnız yapılandırmada bulunan S18'in fiziksel gözlemi

S18 için açık `maintenance.audible:pwm_cycle_time <ad>` izni, DWIN LCD'nin farklı buzzer ayarından değil, kullanıcı profiline dayalı keşif kaydından alınır. Klipper `pwm_cycle_time` durum sorgusunu desteklemediğinden yürütücü uydurma başlangıç durumu veya hayali GET kullanmaz. Baskı/kuyruk güvenliği, ikinci kullanıcı onayı ve korumalı tek POST zorunludur. Komut yanıtı ve sınırlı pulse süresi sonrasında kullanıcıya kısa sesin **çıkıp ardından durduğu** sorulur. Olumlu yanıt, `restore_verified=False` ile `OBSERVED_USER` olarak kaydedilir; `PASSED_USER` veya telemetriyle doğrulanmış geri yükleme sayılmaz. Hata, iptal ve belirsiz iletimde güvenli engelleme korunur. Ayrı ölçüm olmadan fiziksel çıkışın geri yüklendiği kesinleştirilemez; sesi duyup sustuğunu kontrol etmeden olumlu onay verilmez.

## Klipper pin adlarında büyük/küçük harf duyarlılığı (S18)

Klipper'ın `configfile.settings` alanı bölüm adlarını küçük harfe dönüştürürken `configfile.config` özgün bölüm yazılışını korur; `SET_PIN PIN=...` G-code komutu bu özgün adı kullanır. Gerçek Pi'de efektif ayarlarda `pwm_cycle_time buzzer` bulunduğu hâlde Klipper yalnız `PIN=Buzzer` kabul etti; küçük harfli komut `INCONCLUSIVE / script_failed_or_restore_unknown` verdi. S18 ve O03 ön kontrolü artık `configfile.config` için **salt-okunur** GET yapar, açık profil izniyle büyük/küçük harf duyarsız eşleşen tek izinli role ait uygun çıkış bölümünü bulur, fiziksel `pin` değerini efektif ayarlarla karşılaştırır ve tüm KAPALI/pulse/KAPALI komutlarını **özgün yazılışla** üretir. Eksik, çelişkili veya geçersiz kanıt G-code gönderilmeden engellenir. Sabit buzzer adı kullanılmaz, geri yükleme telemetrisi varmış gibi PASS verilmez, F01 değişmez; O03 ise izinli genel görsel çıkışları destekler.

## O04 çoklu piksel geri yükleme ve yönetilen zincirler

O04, LED sayısı sınırlandırılmış, aktarımı toplu yapılan indeksli komutlar ile her pikselin özgün rengini geri yükleyen program oluşturur. Kullanıcı gözlemiyle `PASSED_USER` vermeden önce komut sonrası iki tam geri okumada **bütün** piksellerin özgün değerleriyle eşleşmesi gerekir. Happy Hare/MMU veya LED efekti tarafından yönetilen zincirler ön kontrolde reddedilir; MMU boşta olması LED denetleyicisinin zinciri serbest bıraktığının kanıtı değildir. Yönetilen MMU LED zincirlerinin fiziksel kabulü **BEKLEMEDE** kalır; CI başarısı bunları uyarmaya izin vermez.
