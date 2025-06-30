# AzuraForge Worker Servisi

Bu servis, AzuraForge platformunun ağır iş yükünü taşıyan, arka plan görevlerini işleyen motorudur.

## 🎯 Ana Sorumluluklar

1.  **Görev İşleyici (Celery Worker):**
    *   `Redis`'teki görev kuyruğunu dinler ve `API` tarafından gönderilen yeni görevleri (örn: model eğitimi) alır.
    *   Platforma "eklenti" olarak kurulan AI pipeline'larını (`azuraforge-app-*`) keşfeder ve çalıştırır.

2.  **Raporlama ve Sonuç Üretimi:**
    *   Tamamlanan her deney için sonuçları (`results.json`) ve görsel raporları (`report.md`) oluşturur ve paylaşılan `/reports` dizinine yazar.

3.  **Redis Pub/Sub Yayıncısı:**
    *   Eğitim sırasında, `RedisProgressCallback` aracılığıyla, anlık ilerleme verilerini (epoch, kayıp değeri vb.) ilgili Redis kanalına (`task-progress:*`) yayınlayarak `API` servisinin canlı takip yapmasını sağlar.

## 🛠️ Yerel Geliştirme ve Test

Bu servisi yerel ortamda çalıştırmak ve test etmek için, ana `platform` reposundaki **[Geliştirme Rehberi](../../platform/docs/DEVELOPMENT_GUIDE.md)**'ni takip edin.

Servis bağımlılıkları kurulduktan ve sanal ortam aktive edildikten sonra, aşağıdaki komutla Worker'ı başlatabilirsiniz:

```bash
# worker/ kök dizinindeyken
start-worker
```

Worker, Redis'e bağlanacak ve yeni görevleri beklemeye başlayacaktır.

**Birim Testleri (Yakında):**
Birim testlerini çalıştırmak için:
```bash
pytest
```
