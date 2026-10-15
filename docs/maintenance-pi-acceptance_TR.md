# Maintenance Test Engine — gerçek Raspberry Pi kabulü

[English](maintenance-pi-acceptance.md) · [Backend entegrasyonu](maintenance-backend_TR.md)

**Durum:** GitHub CI regresyonları ve simüle asenkron akışları doğrular, fakat gerçek Pi donanım kabulünü **kanıtlamaz**. Bu belge ve yalnız açıkça çalıştırılan smoke aracı, henüz kullanıcının yazıcısında yürütülmüş test sonuçları değil, saha prosedürüdür.

## 1. Çalışan master'ı koru, yazıcının boşta olduğunu doğrula

Baskı, pause, MMU operasyonu, kalibrasyon veya kararsız bağlantı sırasında feature branch'i devreye alma; `Petrel.service` kesintiye uğratma. Yazıcı config'i, parola, API anahtarı ve gizli verileri GitHub artifact'larına taşıma. Test sırasında güç aç/kapat veya G-code çalıştırma.

Normal Petrel master'da çalışırken, mevcut servis deposunun dalını değiştirmeden ayrı worktree üzerinde salt-okunur ön kabul yapılabilir:

```sh
cd ~/Petrel
git fetch origin feature/maintenance-test-engine
git worktree add --detach /tmp/petrel-maintenance-acceptance origin/feature/maintenance-test-engine
cd /tmp/petrel-maintenance-acceptance
/home/sezgynpi/petrel-env/bin/python tools/validate_maintenance_pi.py --output /tmp/petrel-maintenance-readonly.json
```

Python yolu kabul testi yapılan Pi'nin doğrulanan Petrel sanal ortamıdır. Doğrudan çalıştırılan araç proje import'larını artık PYTHONPATH gerektirmeden bulur. Araç **geçici ikinci Petrel backend bağlantısı** açıp yalnız bilgi kontrollerini yapar; DWIN UI göstermez, heater/motion testi yapmaz, çıkışta tüm bağlantıları kapatır. `READ_ONLY_SMOKE_OK`, S01 ve S08 için güncel/geçerli bilginin okunduğunu gösterir; fiziksel donanım PASS'i **değildir**. `INCOMPLETE` veya `BLOCKED` başarı sayılmaz; nedenini incele. Meşgul kuyruk, baskı, manual probe, MMU, eksik alan veya bağlantı geçişinde sorgu engellenmelidir, güvenlik atlatılmamalıdır.

```sh
git -C ~/Petrel worktree remove /tmp/petrel-maintenance-acceptance
```

## 2. Gerçek servis belleği ve akıcılığı: kontrollü A/B karşılaştırma

Aynı fiziksel yazıcı ve iş yükünde **master** referansını kaydet:

```sh
cd ~/Petrel
PID=$(systemctl show -p MainPID --value Petrel.service)
python3 /tmp/petrel-maintenance-acceptance/tools/measure_petrel_resources.py capture --pid "$PID" --seconds 30 --output /tmp/petrel-master.json
```

Yalnız güvenli, boşta yeniden başlatmada feature branch'i gerçek serviste devreye alıp aynı koşulda tekrar ölç:

```sh
PID=$(systemctl show -p MainPID --value Petrel.service)
python3 tools/measure_petrel_resources.py capture --pid "$PID" --seconds 30 --output /tmp/petrel-feature.json
python3 tools/measure_petrel_resources.py compare --baseline /tmp/petrel-master.json --candidate /tmp/petrel-feature.json --max-uss-kib 1024 --max-rss-kib 1024
```

`Petrel.service` gerçekten beklenen feature checkout'undan çalışıyor olmalı; geçici worktree servis ölçümü yerine geçmez. Ölçümden sonra servisi master'a geri al. Geçici backend smoke'u bellek ölçümü **sırasında** çalıştırma. Aynı boşta ve ayrıca aynı baskı yükünü karşılaştır. DWIN enkoder/kaydırma akıcılığı, UI yeniden çizimi, Maintenance menüsüne giriş/çıkış ve başka menülerde job queue GET yapılmaması manuel denetlenmeli. Açılış bellek tepesi, CPU ve kopma/yeniden bağlanma durumları ayrıca incelenmeli; medyan benchmark bunların tümünü kanıtlamaz.

## Kabul koşulu

Cihaz/OS/Python sürümü, Petrel HEAD SHA, Moonraker/Klipper sürümleri, job queue var/yok bilgisi, gizli veri içermeyen smoke JSON, master/feature RSS/USS/CPU farkları ve manuel UI akıcılığı notlarını kaydet. Gizli config ve anahtarları paylaşma. **Komutlar gerçek Pi üzerinde çalıştırılıp ölçümler geçmeden Pi kabulünü tamamlanmış sayma.** GitHub CI'daki `tests/test_maintenance_pi_acceptance.py` yalnız taklit verilerle çalışır; gerçek yazıcı testinin yerine geçmez.
