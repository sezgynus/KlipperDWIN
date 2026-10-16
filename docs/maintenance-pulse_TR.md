# Maintenance Aşama 8B — süre sınırlı aktüatör komutlarının oluşturulması

[English](maintenance-pulse.md)

Bu katman **yalnız saf komut üreticisidir**: hiçbir metot komut göndermez, test başlatmaz, fiziksel PASS iddiasında bulunmaz veya güvenliği atlatmaz. Yalnız tam eşleşen USER yönlendirmeli keşif kayıtları değişmez `PulseProgram` oluşturabilir. G-code; izin listeli tek uyarım, 150–950 ms `G4` beklemesi ve **tek sınırlı script** içinde başlangıç durumuna dönme komutundan oluşur. Donanımın orijinal firmware durumu yoksa veya güvenilir değilse başlatılamaz. Harici istemciler ya da Klipper yeniden başlatması script'i kesebilir; sonraki executor geri yüklenen çıkışı ayrıca doğrulamadan geri yükleme gözlendi diyemez.

Donanım profilleri: F01 part fan M106 kullanır, RPM değil önceki komutlanan PWM'i geri yükler; F04 fan_generic yalnız tam SET_FAN_SPEED kullanır, template ve güvensiz isimleri reddeder; O03 yalnız açıkça kayıtlı, ölçeği 1 ve başlangıç parlaklığı bilinen case_light PWM içindir; O04 tüm color_data bilgisi bilinen tek LED elemanını SET_LED ile geri yükler, çoklu piksel şeritlerini çalıştırmaz; S18 yalnız OFF durumu ve shutdown_value=0 kanıtı olan kayıtlı buzzer çıkışıdır. Desteklenmeyen donanım engellenir. Klipper G-code sözdizimi resmî [G-Codes](https://www.klipper3d.org/G-Codes.html) belgesinde açıklanır.

Sonraki executor, yazıcıyı boşta tutmalı, Moonraker job queue ve Petrel işlemlerini doğrulamalı, komut gönderimini korumalı, menüye girişte otomatik test başlatmamalı, sonrasında hedefi yeniden okumalı, kullanıcının fiziksel EVET/HAYIR gözlemini status değerlerinden ayırmalı ve doğrulanamayan durumda INCONCLUSIVE sonucunu korumalıdır. Tüm testler yalnız GitHub CI'da yürütülür.

## S18 geri okuma sınırı

Açık izinle etkinleştirilen `pwm_cycle_time` buzzer için Klipper durum geri bildirimi yoktur. Sınırlı script önce KAPALI komutu gönderir, 50 ms bekler, 150 ms ses üretir ve yeniden KAPALI komutu gönderir. Toplam 200 ms'lik program geri yüklemeyi **dener**, ancak fiziksel gerçekleştiğini kanıtlamaz; `restored()` fonksiyonu uydurma durum değeri verilse bile S18'i telemetriyle doğrulanmış saymaz. Yalnız kullanıcı izni verilmiş, efektif yapılandırmada varsayılanı KAPALI olan tam çıkış kabul edilir.

S18 script derleyicisi artık Klipper'ın ham yapılandırmasından ayrı olarak doğrulanan, özgün harf biçimini koruyan `buzzer_command_name` ister. Eksik veya harflerden bağımsız olarak farklı adları reddeder ve bütün `SET_PIN PIN=` komutlarında yalnız bu doğrulanmış yazılışı kullanır.
