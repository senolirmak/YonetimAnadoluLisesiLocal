document.addEventListener('DOMContentLoaded', function() {
    const baslangicId = 'id_baslangic_tarihi';
    const sureId = 'id_sure';
    const hedefId = 'id_goreve_baslama_tarihi';
    const durumId = 'id_durum';

    const baslangicInput = document.getElementById(baslangicId);
    const sureInput = document.getElementById(sureId);
    const hedefInput = document.getElementById(hedefId);
    const durumInput = document.getElementById(durumId);

    if (!baslangicInput || !sureInput || !hedefInput) {
        return;
    }

    function guncelle() {
        const baslangicVal = baslangicInput.value;
        const sureVal = parseInt(sureInput.value, 10);

        if (baslangicVal && !isNaN(sureVal)) {
            // YYYY-MM-DD formatındaki stringi parse et
            const parts = baslangicVal.split('-');
            const year = parseInt(parts[0], 10);
            const month = parseInt(parts[1], 10) - 1; // Aylar 0-11 arasıdır
            const day = parseInt(parts[2], 10);
            
            const dateObj = new Date(year, month, day);
            
            // Tarihe gün ekle
            dateObj.setDate(dateObj.getDate() + sureVal);
            
            // Formatlama: dd.mm.yyyy
            const endDay = String(dateObj.getDate()).padStart(2, '0');
            const endMonth = String(dateObj.getMonth() + 1).padStart(2, '0');
            const endYear = dateObj.getFullYear();

            hedefInput.value = `${endDay}.${endMonth}.${endYear}`;

            // Durum Güncelleme
            if (durumInput) {
                const now = new Date();
                now.setHours(0, 0, 0, 0); // Sadece tarihi karşılaştır
                if (dateObj > now) {
                    durumInput.value = "İzinli";
                    durumInput.style.color = "#dc3545"; // Kırmızı
                    durumInput.style.fontWeight = "bold";
                } else {
                    durumInput.value = "Göreve Başladı";
                    durumInput.style.color = "#28a745"; // Yeşil
                    durumInput.style.fontWeight = "bold";
                }
            }
        }
    }

    baslangicInput.addEventListener('change', guncelle);
    baslangicInput.addEventListener('input', guncelle);
    sureInput.addEventListener('change', guncelle);
    sureInput.addEventListener('input', guncelle);

    // Sayfa yüklendiğinde mevcut değerlerle hesapla
    guncelle();
});
