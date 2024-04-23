// Function to open a tab
function openTab(evt, tabName) {
    // Declare all variables
    var i, tabcontent, tablinks;

    // Get all elements with class="tabcontent" and hide them
    tabcontent = document.getElementsByClassName("tabcontent");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }

    // Get all elements with class="tablinks" and remove the class "active"
    tablinks = document.getElementsByClassName("tablinks");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }

    // Show the current tab, and add an "active" class to the button that opened the tab
    document.getElementById(tabName).style.display = "block";
    evt.currentTarget.className += " active";
}

var autoScrollActive = true;

// Function to simulate console output
function ConsoleOutput() {
    var consoleOutputDiv = document.getElementById('ConsoleOutput');
    var consoleLine = document.createElement('p');
    consoleLine.textContent = 'Console line ' + (consoleOutputDiv.children.length + 1);
    consoleOutputDiv.appendChild(consoleLine);

    if (autoScrollActive) {
        consoleOutputDiv.scrollTop = consoleOutputDiv.scrollHeight;
    }
}

//test line to simulate input. remove in final product
setInterval(ConsoleOutput, 2000);

function checkScroll() {
    var consoleOutputDiv = document.getElementById('ConsoleOutput');
    // Überprüfung, ob der Benutzer ganz nach unten gescrollt hat
    if (consoleOutputDiv.scrollTop + consoleOutputDiv.clientHeight >= consoleOutputDiv.scrollHeight) {
        autoScrollActive = true;
    } else {
        autoScrollActive = false;
    }
}

document.getElementById('ConsoleOutput').addEventListener('scroll', checkScroll);

// Bind the default open tab functionality on window load
window.onload = function () {
    // Click on the first tab link (default open)
    document.getElementsByClassName("tablinks")[0].click();

    // If you want to open a specific tab by default use:
    // document.getElementById("defaultOpen").click();
};

document.querySelector("html").classList.add('js');

var fileInput = document.querySelector(".input-file"),
    button = document.querySelector(".input-file-trigger"),
    the_return = document.querySelector(".file-return");

button.addEventListener("keydown", function (event) {
    if (event.keyCode == 13 || event.keyCode == 32) {
        fileInput.focus();
    }
});
button.addEventListener("click", function (event) {
    fileInput.focus();
    return false;
});
fileInput.addEventListener("change", function (event) {
    the_return.innerHTML = this.value.replace("C:\\fakepath\\", "");
});