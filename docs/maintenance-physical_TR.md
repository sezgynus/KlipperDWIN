# Maintenance Aşama 8C — güvenlik kontrollü fiziksel pulse yürütücüsü

[English](maintenance-physical.md)

`MaintenancePulseController` yalnız kullanıcı isteğiyle çalışan backend durum makinesidir. Desteklenen fiziksel işlemler sadece Aşama 8B'nin hazırladığı `PulseProgram` komutlarıdır; en fazla 950 ms uyarım ve aynı script içinde başlangıç değerine dönüş içerir. Petrel'in mevcut read worker'ını, Moonraker HTTP istemcisini, `postREST` komut kuyruğunu, değişmez discovery'yi, doğrulanmış job queue/operasyon güvenliğini ve açık `GuidedConsentGate` kullanır.

İki ayrı UI eylemi zorunludur: önce keşfedilen testi seçmek (salt okunur kuyruk + başlangıç değeri sorgulanır), ardından kullanıcı hazır olduğunda açıkça onaylamak. **Kullanıcı seçimleri zaman aşımına uğramaz.** Başlatma onayı öncesinde uzun süre beklendiyse eski güvenlik kanıtıyla işlem yapılmaz; onay önce yeni salt-okunur ön kontrol başlatır, ardından kullanıcıdan yeniden çalıştırma onayı alınır. Menü girişi veya keşif asla komut göndermez. Dispatch-time guard Klipper epoch/config değişimini, baskı/pause/manual-probe/MMU işlemlerini, eskimiş kuyruk kanıtını ve bilinmeyen durumu reddeder. `postREST` kısa G-code'u kuyruğa alır; tamamlandıktan sonra ayrıca yapılan GET başlangıç değerine dönüşü doğrulamalıdır. Ancak bundan sonra kullanıcıya fiziksel gözlemi sorulur ve **yalnız açık EVET** `PASSED_USER` üretir. Otomatik PASS veya RPM uydurulmaz.

ÖNEMLİ: Moonraker timeout/bağlantı kopması, script geri alma içeriyor olsa bile komutun çalışıp çalışmadığını belirsiz bırakabilir. Controller `INCONCLUSIVE` döndürür; zamanı aşmış komutu tekrar göndermez. İptal/timeout sonrasında belirsiz komut çalışmaya devam edebilir. Kullanıcı donanımı kontrol etmelidir; yerel rezervasyon harici Moonraker istemcilerini kilitlemez. Bu tasarım hard real-time fail-safe garantisi vermez. Özellikle orijinal çıkış değeri doğrulanamazsa, kuyruk bilinmiyorsa, template aktifse veya son GET başlangıçla uyuşmuyorsa **başarı engellenir**.

LCD arayüzü ve gerçek Pi aktüatör kabulü ayrı doğrulanmalıdır; CI taklitleri fiziksel donanımın çalıştığını kanıtlamaz.

## F12 — güvenli beş kademeli adaptif fan kalkış eşiği

F12, **duruştan kalkış için gözlenen en düşük M106 komutunu** bulur;
gerçek elektriksel PWM veya RPM ölçümü yapmaz. İlk turda %0–50 aralığının
artan beş komutu 2'şer saniye uygulanır. Her kademe, sonunda fanı kapatan
ayrı ve sınırlı bir programla gönderilir. LCD gerçekten gönderilen kademe
numarasını gösterir. İki ayrı Klipper durum okuması kademeler arasında
fan komutunun OFF olduğunu doğrular; fakat bu, pervanenin mekanik olarak
durduğunu kanıtlamaz. Kullanıcı ilk kalkış kademesini veya None seçer;
son başarısız ve ilk başarılı kademe arasında yeniden daraltma yapılır.
Sonraki iterasyon öncesi kullanıcı fiziksel durmayı ayrıca onaylar.

**Zorunlu test koşulu:** Klipper `[fan]` için varsayılan
`kick_start_time: 0.100` saniyedir. Fan OFF durumundan çalıştırılırken,
düşük M106 komutunda bile fan kısa süre **tam güçle** başlatılır.
Bu yüzden F12, etkin Klipper `kick_start_time` değerinin **sıfır**
olduğunu doğrulamadan hiçbir fan komutu göndermez. Alan hiç
tanımlanmamışsa Klipper'ın sıfır olmayan varsayılanı dikkate alınır ve
test engellenir. LCD'de `Set kick_start_time: 0` ve
`RESTART Klipper` uyarısı görünür.

Yazıcı güvenli ve boşta iken, yalnızca ölçüm süresince mevcut
`[fan]` bölümüne `kick_start_time: 0` ekleyip Klipper'da `RESTART`
uygulayın. Testten sonra önceki kick-start ayarını geri getirin ve
yeniden `RESTART` yapın. **Petrel yapılandırmayı kendisi değiştirmez
ve Klipper'ı yeniden başlatmaz.** Kick-start etkin durumdaki asgari
normal kullanım devri farklı bir ölçümdür. `off_below` ve
`max_power` sonuç üzerinde etkili kalır; fiziksel PWM/RPM doğrudan
ölçülmez.

## Kullanıcının hızına göre ilerleyen etkileşimli aşamalar

Maintenance kapsamındaki bütün yönlendirmeli donanım testlerinde
**kullanıcı yanıtları için süre sınırı yoktur**. İlk çalıştırma onayı,
uyarı sonrası gözlem (S18 ses gözlemi dahil) ve F12 fiziksel fan durma
onayı kullanıcı cevap verene veya açıkça iptal edene kadar bekler.
Enkoderin kullanılmaması tek başına `ABORTED`, `INCONCLUSIVE`,
`FAILED_USER` veya `BLOCKED` üretmez. Güvenlik kanıtının üç saniyelik
geçerliliği **UI geri sayımı değil, komut gönderme güvenliği** içindir:
bekleme sonrasında onaya basılması yeni bir salt-okunur güvenlik kontrolü
başlatır ve taze onay ister. Okuma, fiziksel komut ve geri yükleme
doğrulaması için teknik zaman aşımları korunur; bunlar kullanıcı yanıt
süresiyle ilgili değildir.

## Gecikmeli Moonraker geri yükleme telemetrisi (Aşama 8 F01 kabulü)

Gerçek Raspberry Pi kabulünde F01 fan kısa süre çalışmasına rağmen `INCONCLUSIVE / restore_not_verified` görüldü; sonradan yapılan salt-okunur Moonraker sorgusunda `fan.speed=0.0` okundu. Önceki tek GET, G-code yürütmesi/telemetri güncellemesiyle yarışabilir; ancak bu gözlem gecikmenin tam nerede oluştuğunu tek başına kanıtlamaz. Yeni akış, G-code gönderiminden itibaren en az pulse süresi ve ek payı, HTTP tamamlanmasından itibaren de en az 250 ms bekler. Ardından **en az 300 ms aralıkla üst üste iki eşleşen durum GET'i** ister; doğrulama penceresi **altı saniyeyle sınırlıdır**. Bütün okumalar mevcut bounded worker ve UI tick ile yapılır; sleep, yeni worker thread'i veya tekrar G-code gönderimi yoktur.

Ara değer uyuşmazlığı veya geçici okuma hatası düzelebilir; kalıcı uyuşmazlık `restore_value_mismatch`, başarısız okumalar `restore_readback_unavailable`, yeterli kararlı eşleşme olmaması `restore_not_stable`, yazıcı epoch/yapılandırma değişimi `state_changed_during_restore_check` üretir. Zaman aşımı veya belirsizlik hâlinde sonuç **INCONCLUSIVE** kalır; otomatik PASS verilmez. İki eşleşen örnek yalnız bildirilen durumu doğrular, ileride yürütülebilecek kuyruktaki G-code için mutlak güvence değildir; fiziksel gözlem ve kullanıcının açık EVET onayı yine zorunludur. Belirsiz testten sonra çıkışı kontrol etmeden fiziksel pulse tekrarlama.

## Yalnız yapılandırmada bulunan S18'in fiziksel gözlemi

S18 için açık `maintenance.audible:pwm_cycle_time <ad>` izni, DWIN LCD'nin farklı buzzer ayarından değil, kullanıcı profiline dayalı keşif kaydından alınır. Klipper `pwm_cycle_time` durum sorgusunu desteklemediğinden yürütücü uydurma başlangıç durumu veya hayali GET kullanmaz. Baskı/kuyruk güvenliği, ikinci kullanıcı onayı ve korumalı tek POST zorunludur. Komut yanıtı ve sınırlı pulse süresi sonrasında kullanıcıya kısa sesin **çıkıp ardından durduğu** sorulur. Olumlu yanıt, `restore_verified=False` ile `OBSERVED_USER` olarak kaydedilir; `PASSED_USER` veya telemetriyle doğrulanmış geri yükleme sayılmaz. Hata, iptal ve belirsiz iletimde güvenli engelleme korunur. Ayrı ölçüm olmadan fiziksel çıkışın geri yüklendiği kesinleştirilemez; sesi duyup sustuğunu kontrol etmeden olumlu onay verilmez.

## Klipper pin adlarında büyük/küçük harf duyarlılığı (S18)

Klipper'ın `configfile.settings` alanı bölüm adlarını küçük harfe dönüştürürken `configfile.config` özgün bölüm yazılışını korur; `SET_PIN PIN=...` G-code komutu bu özgün adı kullanır. Gerçek Pi'de efektif ayarlarda `pwm_cycle_time buzzer` bulunduğu hâlde Klipper yalnız `PIN=Buzzer` kabul etti; küçük harfli komut `INCONCLUSIVE / script_failed_or_restore_unknown` verdi. S18 ve O03 ön kontrolü artık `configfile.config` için **salt-okunur** GET yapar, açık profil izniyle büyük/küçük harf duyarsız eşleşen tek izinli role ait uygun çıkış bölümünü bulur, fiziksel `pin` değerini efektif ayarlarla karşılaştırır ve tüm KAPALI/pulse/KAPALI komutlarını **özgün yazılışla** üretir. Eksik, çelişkili veya geçersiz kanıt G-code gönderilmeden engellenir. Sabit buzzer adı kullanılmaz, geri yükleme telemetrisi varmış gibi PASS verilmez, F01 değişmez; O03 ise izinli genel görsel çıkışları destekler.

## O04: bağımsız ve eklenti yönetimindeki LED zincirleri

Bağımsız RGB/RGBW zincirlerinde indeksli \`SET_LED\` uyarımı ve her pikselin önceki renginin geri yüklenmesi uygulanır; \`PASSED_USER\` için **hem iki eksiksiz durum geri okuması hem de açık görsel kullanıcı onayı** zorunludur. Komutun başarılı dönmesi veya Klipper'daki renk bilgisi tek başına fiziksel ışık kanıtı değildir.

Standart Happy Hare \`[mmu_leds ...]\` denetleyicileri yazıcıya özel profil olmadan, efektif Klipper eşlemelerinden keşfedilir. \`exit\`, \`entry\`, \`status\`, \`logo\` segmentlerinin tamamı; sınırlandırılmış, çakışmayan farklı fiziksel LED indeksleri ve farklı MMU birimleriyle desteklenir. Yalnız kesin eşlenmiş segmentler test edilir; belirsiz hedefler engellenir. Happy Hare tarafından yönetilen O04, doğrudan \`SET_LED\` veya \`MMU_LED ENABLE=0\` yerine süreli, birim bazlı \`MMU_SET_LED ... DURATION=0.40\` kullanır. İlgili her birimin LED yönetimi açık ve okunabilir, MMU boşta olmalıdır; çift kullanıcı onayı ve kuyruk güvenlik kontrolü aynen geçerlidir. Test sonrası kontrol politikası geri okuması LED renklerinin geri döndüğünü kanıtlamadığından kullanıcı olumlu gözlemi \`OBSERVED_USER\`, \`restore_verified=False\` üretir. Otomatik fiziksel PASS yoktur. Gerçek donanımda kullanıcı gözlemi yapılana kadar fiziksel kabul beklemededir.

**O04 Happy Hare sayısal UNIT kanıtı:** `[mmu_leds AD]` bölümünün eki ile kullanıcıya görünen `mmu_machine.unit_N.name` zorunlu olarak aynı kimlik değildir. Sayısal `UNIT`, doğrulanmış sıralı yapılandırma listesinden veya benzersiz tek birim kanıtından (canlı `num_units=1`, tek `unit_0` kaydı, tam olarak tek MMU LED denetleyicisi) çözülür. İkinci durumda ad eşleşmesi gerekmeksizin güvenli `UNIT=0` elde edilir. Çok birimli sistemlerde gerçek eşleme doğrulanmadan tahmin yapılmaz. Keşifte ve G-code öncesi son kontrolde eksik/belirsiz/çelişkili kanıt LED'lere dokunulmadan reddedilir.

### O04 tam parlaklık RGB gözlemi

Kullanıcı onaylı O04, eşlenmiş bütün RGB LED'lerde **kırmızı, mavi, yeşil ve beyazı** sırayla 650'şer ms gösterir ve ardından önceki duruma/politikaya döner. Bağımsız zincir her indeksli renk karesini bir defada aktarır ve bütün LED'lerin eski değerlerini geri yükler. Happy Hare, süreli efektlerin ertelenmesi probleminden kaçınmak için 650 ms arayla dört ayrı 400 ms'lik otomatik sona eren efekt kullanır; HH kontrolünü kapatmaz. Her iki yöntemde kullanıcı **dört rengin tamamını tüm eşlenmiş LED'lerde** gördüğünü ayrıca onaylamalıdır. Yalnız tek renkli LED nesneleri RGB testine uygun değildir. Tam parlak beyaz tepe akımını artırabilir; zincirin güç beslemesi yeterli olmalıdır.

**Renk sırası ön kontrolü:** Klipper RGB/RGBW çıkışlarında efektif color_order değeri metin yerine liste/tuple olabilir (config.getlist yapısı). İki biçim de her piksel için aynı sıkı denetimden geçirilir. Bozuk veya karışık renk düzeni G-code öncesinde BLOCKED üretir. LCD güvenli BLOCKED sonucunu korurken Petrel günlüğüne "Maintenance physical preflight blocked" teknik nedeni yazılır; komut gönderilmez.
