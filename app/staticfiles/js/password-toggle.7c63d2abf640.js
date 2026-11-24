/* Show / hide a password field.
   <button type="button" class="pwd-toggle" data-toggle-password="#id">◡—◡</button> */
document.addEventListener('click', function (event) {
  var button = event.target.closest('[data-toggle-password]');
  if (!button) { return; }
  var input = document.querySelector(button.getAttribute('data-toggle-password'));
  if (!input) { return; }
  var reveal = input.type === 'password';
  input.type = reveal ? 'text' : 'password';
  button.textContent = reveal ? '●—●' : '◡—◡';
  button.setAttribute('aria-pressed', reveal ? 'true' : 'false');
});