document.addEventListener('DOMContentLoaded', function() {
            const form = document.getElementById('generateForm');
            const generateBtn = document.getElementById('generateBtn');
            const loadingOverlay = document.getElementById('loadingOverlay');
            const dateInput = document.querySelector('input[name="date"]');

            form.addEventListener('submit', function(e) {
                // Validate date input
                if (!dateInput.value) {
                    e.preventDefault();
                    dateInput.focus();
                    return;
                }

                // Show loading animation
                showLoading();
                
                // Add loading state to button
                generateBtn.classList.add('loading');
                generateBtn.disabled = true;

                // Note: The form will submit normally after this
                // The loading animation will continue until the page reloads/redirects
            });

            function showLoading() {
                loadingOverlay.classList.add('show');
                document.body.style.overflow = 'hidden'; // Prevent scrolling
            }

            function hideLoading() {
                loadingOverlay.classList.remove('show');
                generateBtn.classList.remove('loading');
                generateBtn.disabled = false;
                document.body.style.overflow = 'auto'; // Re-enable scrolling
            }

            // Hide loading if user navigates back or if there's an error
            window.addEventListener('pageshow', function(event) {
                if (event.persisted) {
                    hideLoading();
                }
            });

            // Optional: Hide loading after a timeout as fallback
            let loadingTimeout;
            form.addEventListener('submit', function() {
                // Clear any existing timeout
                if (loadingTimeout) {
                    clearTimeout(loadingTimeout);
                }
                
                // Set timeout to hide loading after 30 seconds as fallback
                loadingTimeout = setTimeout(function() {
                    hideLoading();
                    console.warn('Loading animation timed out after 30 seconds');
                }, 30000);
            });
        });