document.addEventListener("DOMContentLoaded", function() {
        var slider = document.getElementById("id_max_shifts");
        var output = document.getElementById("slider_value");
        if (slider && output) {
            output.textContent = slider.value;
            slider.oninput = function() {
                output.textContent = this.value;
            }
        }
    });