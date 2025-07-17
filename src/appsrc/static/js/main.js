function getComputedBackgroundColor(element) {
  var tempElement = document.createElement('div');
  tempElement.classList.add(element);
  document.body.appendChild(tempElement);
  var computedColor = window.getComputedStyle(tempElement).getPropertyValue('background-color');
  document.body.removeChild(tempElement);
  return computedColor;
}

function getComputedColor(element) {
  var tempElement = document.createElement('div');
  tempElement.classList.add(element);
  document.body.appendChild(tempElement);
  var computedColor = window.getComputedStyle(tempElement).getPropertyValue('color');
  document.body.removeChild(tempElement);
  return computedColor;
}

function parseRGBA(color) {
  var rgba = color.substring(color.indexOf('(') + 1, color.lastIndexOf(')')).split(',');
  return {
    r: parseInt(rgba[0].trim()),
    g: parseInt(rgba[1].trim()),
    b: parseInt(rgba[2].trim()),
  };
}

function rgbaWithAlpha(color) {
  var components = color.split(",");
  components[3] = "1)";
  return components.join(",");
}

function interpolateColor(color1, color2, factor) {
  var c1 = parseRGBA(color1);
  var c2 = parseRGBA(color2);
  var r = Math.round(c1.r + (c2.r - c1.r) * factor);
  var g = Math.round(c1.g + (c2.g - c1.g) * factor);
  var b = Math.round(c1.b + (c2.b - c1.b) * factor);
  var a = 0.25 + (0.65 - 0.25) * factor;
  return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
}

function deleteMessage(button) {
  var alertDiv = button.closest('.alert');
  if (alertDiv) {
    alertDiv.remove();
  }
};
function toggleChevronIcon(button) {
  const chevronIcon = button.querySelector('.bi-chevron-down');
  chevronIcon.classList.toggle('flip');
  button.setAttribute('aria-expanded', chevronIcon.classList.contains('flip'));
}
function loadTab(tabId, endpoint) {
  var tabContent = document.getElementById(tabId);
  if (!tabContent.hasAttribute('data-loaded')) {
    var iframe = document.createElement('iframe');
    iframe.src = endpoint;
    iframe.frameBorder = 0;
    iframe.width = '100%';
    iframe.height = '700px';
    tabContent.appendChild(iframe);
    tabContent.setAttribute('data-loaded', 'true');
    iframe.addEventListener('load', function () {
      var links = iframe.contentDocument.querySelectorAll('a');
      links.forEach(function (link) {
        link.setAttribute('target', '_top');
      });
    });
  }
}

function updateZoomTooltip(level) {
  const zoomButton = document.getElementById('zoomButton');
  try {
    zoomButton.textContent = ` ${level}%`;
  } catch (error) {
    
  }
}

function toggleZoom(event) {
  let currentZoomLevel = parseFloat(localStorage.getItem('zoomLevel')) || 100;
  currentZoomLevel += 10;
  if (currentZoomLevel > 200) {
    currentZoomLevel = 100;
  }
  localStorage.setItem('zoomLevel', currentZoomLevel);
  document.body.style.zoom = currentZoomLevel + '%';
  updateZoomTooltip(currentZoomLevel);
}

var warningBackgroundColor = getComputedBackgroundColor('bg-success');
var dangerBackgroundColor = getComputedBackgroundColor('bg-danger');
warningBackgroundColor = interpolateColor(warningBackgroundColor, dangerBackgroundColor, 0); //Convert to RGBA
dangerBackgroundColor = interpolateColor(warningBackgroundColor, dangerBackgroundColor, 1);
var errorLevels = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
var numLevels = errorLevels.length - 1;
var colorMap = {};
for (var i = 0; i < errorLevels.length; i++) {
  var factor = i / numLevels;
  var interpolatedColor = interpolateColor(warningBackgroundColor, dangerBackgroundColor, factor);
  colorMap[errorLevels[i]] = interpolatedColor;
}
colorMap['MODERATE'] = colorMap['MEDIUM'];


function openIframeModal(title, url) {
  const iframe = document.getElementById('iframeViewer');
  iframe.src = url;
  
  const modal = new bootstrap.Modal(document.getElementById('iframeModal'));
  const modalLabel = document.getElementById('iframeModalLabel');
  modalLabel.textContent = title;

  modal.show();

  const modalEl = document.getElementById('iframeModal');
  modalEl.addEventListener('hidden.bs.modal', function () {
      iframe.src = '';
  }, { once: true });
}

$(document).ready(function(){
    let currentZoomLevel = parseFloat(localStorage.getItem('zoomLevel')) || 100;
    document.body.style.zoom = currentZoomLevel + '%';
    updateZoomTooltip(currentZoomLevel);
    
    function loadDynamicIframe(frameId) {
      var tabContent = document.getElementById(frameId);
      if (tabContent.querySelector('iframe')) {
        return;
      }
      var iframe = document.createElement('iframe');
      iframe.src = tabContent.getAttribute('data-value');
      iframe.frameBorder = 0;
      iframe.width = '100%';
      iframe.height = '600px';
      iframe.minHeight = '600px';
      tabContent.appendChild(iframe);
    }
    $('[id$="_dynamiciframe"]').each(function () {
      loadDynamicIframe(this.id);
    });

    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
      return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

$(document).ready(function () {
  var link_color = getComputedColor('text-light');
  var highlight_color = getComputedColor('secondary');
  // Inject CSS for hover/focus if needed
  const styleTag = document.createElement("style");
  styleTag.innerHTML = `
    .editor-toolbar a:hover,
    .editor-toolbar a:focus,
    .editor-toolbar a:active {
      background-color: ${highlight_color} !important;
      border-radius: 0 !important;
    }
  `;
  document.head.appendChild(styleTag);

  $('.editor-toolbar').each(function () {
    $(this).addClass('bg-dark text-light');
    this.style.borderRadius = '0px';

    $(this).find('a').each(function () {
      this.style.setProperty('color', link_color, 'important');
      this.style.setProperty('border-radius', '0', 'important');
    });
  });
});
