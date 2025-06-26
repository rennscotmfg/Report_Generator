document.addEventListener('DOMContentLoaded', function() {
            const form = document.getElementById('generateForm');
            const generateBtn = document.getElementById('generateBtn');
            const loadingOverlay = document.getElementById('loadingOverlay');
            const dateInput = document.getElementById('dateInput');

            // Initialize Flatpickr
            const datePicker = flatpickr(dateInput, {
                dateFormat: "Y-m-d", // This matches the format your backend expects
                defaultDate: "today",
                maxDate: "today", // Prevent selecting future dates
                theme: "dark",
                allowInput: false, // Prevent manual typing
                clickOpens: true,
                // Custom styling to match your theme
                onReady: function(selectedDates, dateStr, instance) {
                    // Add custom class to the calendar
                    instance.calendarContainer.classList.add('custom-flatpickr');
                }
            });

            form.addEventListener('submit', function(e) {
                // Validate date input
                if (!dateInput.value) {
                    e.preventDefault();
                    datePicker.open(); // Open calendar if no date selected
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