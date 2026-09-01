function printToOutput(text) {
    const outputArea = document.getElementById('output-area');
    outputArea.classList.add('fade-out');
    setTimeout(() => {
        outputArea.textContent = text;
        outputArea.classList.remove('fade-out');
        outputArea.classList.add('fade-in');
        setTimeout(() => {
            outputArea.classList.remove('fade-in');
        }, 400);
    }, 400);

    // Show/hide processing ring based on text content
    const processingRing = document.querySelector('.processing-ring');
    if (processingRing) {
        if (text && text.toLowerCase().includes('processing')) {
            processingRing.classList.add('active');
        } else {
            // Hide processing ring for any other text (including empty, listening, etc.)
            processingRing.classList.remove('active');
        }
    }
}

// NEW: Function to update the bottom-left output
function updateBottomLeftOutput(text) {
    const outputElement = document.getElementById('bottom-left-text');
    const container = document.getElementById('bottom-left-output');
    const isScrolledToBottom = (container.scrollHeight - container.clientHeight <= container.scrollTop + 1);
    outputElement.textContent = text;
    // Adjust vertical position based on text length (optional)

    const length = text.length;

    if (length > 200) {
        container.style.bottom = '50px'; // Example: move up if text is very long
    } else {
        container.style.bottom = '20px'; // Reset default
    }

    if (isScrolledToBottom) {
        // If already at the bottom, scroll to the new bottom
        container.scrollTop = container.scrollHeight;
    }

}
window.onload = function () {
    if (typeof eel !== 'undefined' && typeof eel.ui_ready === 'function') {
        eel.ui_ready();
    }
};

// Function to clear all widgets from the interface
function clearAllWidgets() {
    // Find all elements with 'widget' class
    const widgets = document.querySelectorAll('.widget');
    const count = widgets.length;

    // Go through WidgetManager where we can. Sweeping the DOM alone leaves
    // WidgetManager.widgets holding every widget that was just removed, and
    // getAllWidgets() reads that registry first - so anything asking what is
    // on screen would be told about widgets that are no longer there.
    if (window.WidgetManager && typeof window.WidgetManager.clearAll === 'function') {
        window.WidgetManager.clearAll();
        return count;
    }

    // Fallback: animate each widget's disappearance before removal
    widgets.forEach(widget => {
        // First remove the 'active' class to trigger fade-out animation
        widget.classList.remove('active');

        // Wait for the fade-out animation to complete before removing from DOM
        setTimeout(() => {
            if (widget && widget.parentNode) {
                widget.parentNode.removeChild(widget);
            }
        }, 300); // Match this to your CSS transition time (300ms)
    });

    // Return the count of widgets that were cleared
    return count;
}

// Function to show processing animation
function showProcessingAnimation() {
    const processingRing = document.querySelector('.processing-ring');
    if (processingRing) {
        processingRing.classList.add('active');
    }
}

// Function to hide processing animation
function hideProcessingAnimation() {
    const processingRing = document.querySelector('.processing-ring');
    if (processingRing) {
        processingRing.classList.remove('active');
    }
}

// Expose the function to eel so it can be called from Python
// Close and remove a single widget by its id, without disturbing any others.
// Exposed so Python can retire one widget it created earlier — the tool
// activity log, once a turn has finished — without clearAllWidgets(), which
// would also take down anything the model is actively showing.
function closeWidgetById(widgetId) {
    const element = document.getElementById(widgetId);
    if (!element) return false;
    if (window.WidgetManager && window.WidgetManager.widgets) {
        const widget = window.WidgetManager.widgets.find(w => w.element === element);
        if (widget) {
            widget.close();
            return true;
        }
    }
    // No WidgetManager entry found (shouldn't normally happen) — remove the
    // DOM node directly rather than leave a dead widget on screen.
    element.remove();
    return true;
}
eel.expose(closeWidgetById);

eel.expose(clearAllWidgets);
eel.expose(printToOutput);
eel.expose(updateWidgetContent);
function updateWidgetContent(widgetId, content) {
    try {
        const widget = document.getElementById(widgetId);
        if (widget) {
            const contentEl = widget.querySelector('.widget-content');
            if (contentEl) {
                // Store scroll position before update (to check if user scrolled up)
                const wasScrolledToBottom = contentEl.scrollHeight - contentEl.clientHeight <= contentEl.scrollTop + 10;
                
                // If content contains HTML-like structure, preserve it
                if (content.includes('<') || content.includes('\n')) {
                    // For multi-line content, use pre-wrap to preserve formatting
                    contentEl.style.whiteSpace = 'pre-wrap';
                    contentEl.textContent = content;
                } else {
                    contentEl.textContent = content;
                }
                
                // Auto-scroll to bottom if:
                // 1. User was already at the bottom, OR
                // 2. This is a browser progress widget (always auto-scroll)
                const widgetTitle = widget.querySelector('.widget-title')?.textContent || '';
                const isBrowserProgress = widget.getAttribute('data-type') === 'text' && 
                                         widgetTitle.includes('Browser Automation');
                
                // Use requestAnimationFrame to ensure DOM is updated before scrolling
                requestAnimationFrame(() => {
                    if (wasScrolledToBottom || isBrowserProgress) {
                        // Scroll to bottom
                        contentEl.scrollTop = contentEl.scrollHeight;
                    }
                });
                
                return true;
            }
        }
        return false;
    } catch (error) {
        console.error('Error updating widget content:', error);
        return false;
    }
}
eel.expose(updateBottomLeftOutput);
eel.expose(showProcessingAnimation);
eel.expose(hideProcessingAnimation);

// Video counter for numbering video widgets
let videoCounter = 0;
// Image counter for numbering image widgets
let imageCounter = 0;

// Function to get next video number
function getNextVideoNumber() {
    videoCounter++;
    return videoCounter;
}

// Function to get next image number
function getNextImageNumber() {
    imageCounter++;
    return imageCounter;
}

// Function to reset video counter (if needed)
function resetVideoCounter() {
    videoCounter = 0;
}

// Function to reset image counter (if needed)
function resetImageCounter() {
    imageCounter = 0;
}

// Make functions available globally
window.getNextVideoNumber = getNextVideoNumber;
window.resetVideoCounter = resetVideoCounter;
window.getNextImageNumber = getNextImageNumber;
window.resetImageCounter = resetImageCounter;

// Expose to eel so Python can get the next video number
eel.expose(getNextVideoNumber);
eel.expose(getNextImageNumber);

// Global z-index tracker for widget layering
// Base z-index for widgets (matches CSS default)
let widgetZIndexBase = 1000;
// Track the highest z-index currently in use
let highestWidgetZIndex = widgetZIndexBase;

// Function to get the next highest z-index for a widget
function getNextWidgetZIndex() {
    highestWidgetZIndex += 1;
    return highestWidgetZIndex;
}

// Function to get the current highest z-index from all widgets
function getCurrentHighestWidgetZIndex() {
    const widgets = document.querySelectorAll('.widget');
    let maxZIndex = widgetZIndexBase;
    
    widgets.forEach(widget => {
        const zIndex = parseInt(window.getComputedStyle(widget).zIndex, 10);
        if (!isNaN(zIndex) && zIndex > maxZIndex) {
            maxZIndex = zIndex;
        }
    });
    
    return maxZIndex;
}

function getYouTubeVideoId(url) {
    try {
        // Decode URL to handle encoded characters like \u0026
        url = decodeURIComponent(url);

        // Regex to match various YouTube URL formats
        const regExp = /(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:v\/|embed\/|watch\?v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
        const match = url.match(regExp);

        const videoId = match ? match[1] : null;
        console.log("Extracted Video ID:", videoId); // Debugging
        return videoId;
    } catch (error) {
        console.error("Error extracting video ID:", error, url);
        return null;
    }
}

// Make function available globally for drag/drop handler
window.getYouTubeVideoId = getYouTubeVideoId;

// Function to start speaking animation
function startSpeakingAnimation() {
    const jarvisContainer = document.querySelector('.jarvis-container');
    if (jarvisContainer) {
        jarvisContainer.classList.add('speaking');
    }
}

// Function to stop speaking animation
function stopSpeakingAnimation() {
    const jarvisContainer = document.querySelector('.jarvis-container');
    if (jarvisContainer) {
        jarvisContainer.classList.remove('speaking');
        // Reset custom properties
        jarvisContainer.style.setProperty('--audio-amplitude', '0');
    }
}

// Mirrors start/stopSpeakingAnimation for the other direction: the orb pulses
// while the hotword listener is recording what was said after "Hey Jarvis",
// so hearing the wake word is visible immediately rather than only once a
// transcript comes back a moment later.
function startListeningAnimation() {
    const jarvisContainer = document.querySelector('.jarvis-container');
    if (jarvisContainer) {
        jarvisContainer.classList.add('listening');
    }
}

function stopListeningAnimation() {
    const jarvisContainer = document.querySelector('.jarvis-container');
    if (jarvisContainer) {
        jarvisContainer.classList.remove('listening');
    }
}
eel.expose(startListeningAnimation);
eel.expose(stopListeningAnimation);

// Function to update animation based on audio amplitude (0-1)
function updateSpeakingAmplitude(amplitude) {
    const jarvisContainer = document.querySelector('.jarvis-container');
    if (jarvisContainer) {
        // Reduce amplitude by half
        amplitude = amplitude * 0.5;

        // Amplify the amplitude for more visible effect (0-1 becomes 0-1.7 for scale)
        const outerScaleMultiplier = 0.5; // Outer ring scales up to 1.5x
        const innerScaleMultiplier = 0.7; // Inner ring scales up to 1.7x
        const baseScale = 1.0;

        // Calculate scale based on amplitude with slight enhancement
        const enhancedAmplitude = Math.pow(amplitude, 0.8); // More responsive curve
        const outerScale = baseScale + (enhancedAmplitude * outerScaleMultiplier);
        const innerScale = baseScale + (enhancedAmplitude * innerScaleMultiplier);

        // Update CSS custom properties
        jarvisContainer.style.setProperty('--audio-amplitude', enhancedAmplitude);
        jarvisContainer.style.setProperty('--outer-scale', outerScale);
        jarvisContainer.style.setProperty('--inner-scale', innerScale);

        // Directly update transforms for smoother animation
        const outerCircle = jarvisContainer.querySelector('.outer-circle');
        const innerCircle = jarvisContainer.querySelector('.inner-circle');

        if (outerCircle) {
            outerCircle.style.transform = `scale(${outerScale})`;
            // More pronounced opacity change for more depth
            outerCircle.style.opacity = 0.85 + (enhancedAmplitude * 0.15);
        }
        if (innerCircle) {
            innerCircle.style.transform = `translate(-50%, -50%) scale(${innerScale})`;
            // More pronounced opacity change for more depth
            innerCircle.style.opacity = 0.88 + (enhancedAmplitude * 0.12);
        }

        // Update glow intensity - more pronounced
        const baseGlow = 30;
        const maxGlow = 85;
        const baseGlowAlpha = 0.6;
        const maxGlowAlpha = 1.0;
        const baseInsetGlow = 30;
        const maxInsetGlow = 55;
        const baseInsetAlpha = 0.4;
        const maxInsetAlpha = 0.7;

        jarvisContainer.style.boxShadow = `
            0 0 ${baseGlow + (enhancedAmplitude * (maxGlow - baseGlow))}px rgba(13, 166, 255, ${baseGlowAlpha + (enhancedAmplitude * (maxGlowAlpha - baseGlowAlpha))}),
            0 0 ${(baseGlow + (enhancedAmplitude * (maxGlow - baseGlow))) * 1.6}px rgba(0, 149, 255, ${baseGlowAlpha + (enhancedAmplitude * (maxGlowAlpha - baseGlowAlpha)) * 0.95}),
            0 0 ${(baseGlow + (enhancedAmplitude * (maxGlow - baseGlow))) * 2.2}px rgba(0, 149, 255, ${(baseGlowAlpha + (enhancedAmplitude * (maxGlowAlpha - baseGlowAlpha))) * 0.6}),
            inset 0 0 ${baseInsetGlow + (enhancedAmplitude * (maxInsetGlow - baseInsetGlow))}px rgba(0, 149, 255, ${baseInsetAlpha + (enhancedAmplitude * (maxInsetAlpha - baseInsetAlpha))})
        `;

        // Update container-glow element to sync with audio (works for both normal and compact mode since everything scales)
        const containerGlow = jarvisContainer.querySelector('.container-glow');
        if (containerGlow) {
            // Normal mode glow values (matches the pulseGlow animation pattern)
            const normalBaseGlow = 20;
            const normalMaxGlow = 30;
            const normalBaseSpread = 5;
            const normalMaxSpread = 15;
            const normalBaseAlpha = 0.93;
            const normalMaxAlpha = 0.9;

            const normalGlowSize = normalBaseGlow + (enhancedAmplitude * (normalMaxGlow - normalBaseGlow));
            const normalGlowSpread = normalBaseSpread + (enhancedAmplitude * (normalMaxSpread - normalBaseSpread));
            const normalGlowAlpha = normalBaseAlpha + (enhancedAmplitude * (normalMaxAlpha - normalBaseAlpha));

            containerGlow.style.boxShadow = `0 0 ${normalGlowSize}px ${normalGlowSpread}px rgba(13, 166, 255, ${normalGlowAlpha})`;
        }
    }
}

// Expose speaking animation functions to eel
eel.expose(startSpeakingAnimation);
eel.expose(stopSpeakingAnimation);
eel.expose(updateSpeakingAmplitude);

// Debug function to test weather widget
function testWeatherWidget() {
    console.log("Testing weather widget...");
    eel.test_weather_widget()(function (result) {
        console.log("Weather widget test result:", result);
    });
}

// Expose test function globally
window.testWeatherWidget = testWeatherWidget;

// Create widget function - modified to work synchronously with eel
function createWidget(id, title, type, content, x = 100, y = 100, customWidth, customHeight, groupId = null) {
    // Log immediately to verify function is called - this should appear in browser console
    console.log('=== createWidget CALLED ===', { id, title, type });
    console.log('Arguments:', arguments);
    
    try {
        console.log('=== createWidget called ===');
        console.log('Creating widget:', { id, title, type, x, y, customWidth, customHeight, groupId });
        console.log('Content type:', typeof content, 'Content:', content);

        // Ensure x and y are numbers
        x = typeof x === 'number' ? x : 100;
        y = typeof y === 'number' ? y : 100;

        // Generate group ID if not provided (for backward compatibility)
        if (!groupId) {
            groupId = `group_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        }

        // For image widgets with URLs, pre-validate in browser before creating widget
        if (type === 'image' && content && content.startsWith('http')) {
            // Pre-load image to verify it actually works in browser
            const testImg = new Image();
            let timeout;
            let widgetCreated = false;
            
            const createWidgetIfValid = () => {
                if (widgetCreated) return;
                widgetCreated = true;
                
                if (timeout) clearTimeout(timeout);
                
                // Verify image loaded successfully
                if (testImg.naturalWidth === 0 || testImg.naturalHeight === 0) {
                    console.log('Image preload failed: invalid dimensions, skipping widget');
                    return;
                }
                
                // Image is valid, create the widget
                try {
                    const widget = new Widget(id, title, type, content, x, y, customWidth, customHeight, groupId);
                    
                    // Register with layout manager
                    if (window.WidgetManager) {
                        window.WidgetManager.register(widget);
                        console.log('Widget registered with WidgetManager');
                    } else {
                        console.warn('WidgetManager not available');
                    }
                    
                    console.log('Widget created successfully after browser validation:', id);
                } catch (error) {
                    console.error('Error creating widget after validation:', error);
                }
            };
            
            // Set timeout - if image doesn't load in 5 seconds, skip it
            timeout = setTimeout(() => {
                if (!widgetCreated) {
                    console.log('Image preload timeout, skipping widget:', content.substring(0, 50));
                    widgetCreated = true; // Mark as handled to prevent double creation
                }
            }, 5000);
            
            testImg.onload = createWidgetIfValid;
            testImg.onerror = () => {
                if (!widgetCreated) {
                    console.log('Image preload failed in browser, skipping widget:', content.substring(0, 50));
                    widgetCreated = true;
                    if (timeout) clearTimeout(timeout);
                }
            };
            
            // Start loading
            testImg.crossOrigin = 'anonymous';
            testImg.referrerPolicy = 'no-referrer';
            testImg.src = content;
            
            // Return widget_id string since widget creation is async
            // This ensures eel gets a valid return value
            return id;
        } else {
            // For non-image widgets or local images, create immediately
            console.log('Creating non-image widget, type:', type);
            const widget = new Widget(id, title, type, content, x, y, customWidth, customHeight, groupId);
            console.log('Widget instance created:', widget);

            // Register with layout manager so widgets are placed intuitively
            if (window.WidgetManager) {
                window.WidgetManager.register(widget);
                console.log('Widget registered with WidgetManager');
            } else {
                console.warn('WidgetManager not available');
            }

            console.log('Widget created successfully:', id);
            return widget;
        }
    } catch (error) {
        console.error('Error creating widget:', error);
        console.error('Stack trace:', error.stack);
        throw error;
    }
}

// Expose the createWidget function to eel (after it's defined)
eel.expose(createWidget);

// Make function available globally for drag/drop handler
window.createWidget = createWidget;

// Expose function to set focus on a widget group
eel.expose(setWidgetFocus);
function setWidgetFocus(groupId, addToFocused = false) {
    if (window.WidgetManager) {
        window.WidgetManager.setFocus(groupId, addToFocused);
    }
}

class Widget {
    constructor(id, title, type, content, x, y, customWidth, customHeight, groupId = null) {
        this.element = this.createWidget(id, title, type, content);
        this.customWidth = customWidth;
        this.customHeight = customHeight;
        this.groupId = groupId || `group_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        this.isPositioned = false; // Track if widget has been positioned
        // Optionally remember a preferred position (used later by layout manager)
        if (typeof x === 'number' && typeof y === 'number') {
            this.preferredX = x;
            this.preferredY = y;
        }

        // For time widgets, ensure font size is set before appending to DOM
        if (type === 'time') {
            const contentEl = this.element.querySelector('.widget-content');
            if (contentEl) {
                contentEl.style.setProperty('font-size', '3em', 'important');
                contentEl.style.setProperty('font-weight', '300', 'important');
                contentEl.style.setProperty('transition', 'none', 'important');
            }
        }

        // Append early so measurements work
        document.body.appendChild(this.element);

        // Set initial z-index for the widget
        const initialZIndex = getNextWidgetZIndex();
        this.element.style.setProperty('z-index', initialZIndex, 'important');
        this.element.dataset.widgetZIndex = initialZIndex;

        // Basic setup
        this.setupDragging();
        this.setupResizing();
        this.setupRightClickClose();
        this.setupClickToFocus();

        // Size the widget before positioning
        this.autoSize();

        // Compute Jarvis center as origin for entrance animation if available
        const jarvis = document.querySelector('.jarvis-container');
        let originX = (window.innerWidth - this.element.offsetWidth) / 2;
        let originY = (window.innerHeight - this.element.offsetHeight) / 2;
        if (jarvis) {
            const r = jarvis.getBoundingClientRect();
            originX = r.left + (r.width / 2) - (this.element.offsetWidth / 2);
            originY = r.top + (r.height / 2) - (this.element.offsetHeight / 2);
        }

        // Place element initially at the origin (jarvis center)
        this.element.style.left = `${Math.max(8, Math.min(originX, window.innerWidth - this.element.offsetWidth - 8))}px`;
        this.element.style.top = `${Math.max(8, Math.min(originY, window.innerHeight - this.element.offsetHeight - 8))}px`;

        // Activate after a short delay; actual positioning is handled
        // globally by WidgetManager.layoutWidgets to avoid overlap
        requestAnimationFrame(() => {
            setTimeout(() => {
                this.element.classList.add('active');
            }, 20);
        });
    }

    createWidget(id, title, type, content) {
        const widget = document.createElement('div');
        widget.className = 'widget';
        widget.id = id;
        widget.setAttribute('data-type', type);

        // Add corner marks
        const cornerTopLeft = document.createElement('div');
        cornerTopLeft.className = 'widget-corner widget-corner-top-left';
        widget.appendChild(cornerTopLeft);

        const cornerTopRight = document.createElement('div');
        cornerTopRight.className = 'widget-corner widget-corner-top-right';
        widget.appendChild(cornerTopRight);

        const cornerBottomLeft = document.createElement('div');
        cornerBottomLeft.className = 'widget-corner widget-corner-bottom-left';
        widget.appendChild(cornerBottomLeft);

        const cornerBottomRight = document.createElement('div');
        cornerBottomRight.className = 'widget-corner widget-corner-bottom-right';
        widget.appendChild(cornerBottomRight);

        const header = document.createElement('div');
        header.className = 'widget-header';

        const titleEl = document.createElement('div');
        titleEl.className = 'widget-title';
        titleEl.textContent = title;

        // Add transcript indicator for video widgets (overlay on top of title)
        if (type === 'video') {
            titleEl.style.position = 'relative'; // Make title a positioning context

            const transcriptIndicator = document.createElement('div');
            transcriptIndicator.className = 'transcript-indicator';
            // Use SVG icon instead of emoji
            transcriptIndicator.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" opacity="0.3"/>
                    <path d="M12 6v6l4 2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
            `;
            transcriptIndicator.title = 'Checking transcript availability...';
            titleEl.appendChild(transcriptIndicator);

            // Store reference for later update
            widget.dataset.transcriptIndicator = 'true';
        }

        // We'll keep the close button but make it less visually prominent or remove it
        // Option 1: Keep but make less visible
        const closeBtn = document.createElement('div');
        closeBtn.style.display = 'none';

        // Option 2: Remove close button entirely
        // Uncomment the line below and comment out the closeBtn code above if you want to remove it completely
        // const closeBtn = document.createElement('div');

        header.appendChild(titleEl);
        header.appendChild(closeBtn);

        const contentEl = document.createElement('div');
        // For time, timer, alarm, and reminder widgets, use 'text' class so it styles like a text widget
        // Notes widgets get their own class
        const contentClass = (type === 'time' || type === 'timer' || type === 'alarm' || type === 'reminder' || type === 'gesture_control') ? 'widget-content text' : `widget-content ${type}`;
        contentEl.className = contentClass;
        
        // For time, timer, alarm, and reminder widgets, set font size IMMEDIATELY before any content is added
        // and before the element is added to DOM - this prevents the "growing" animation
        if (type === 'time' || type === 'timer' || type === 'alarm' || type === 'reminder') {
            // Set styles immediately with !important to override any CSS
            // Use cssText to set all at once before element is visible
            // Reminders use slightly smaller font size
            const fontSize = type === 'reminder' ? '2.2em' : '3em';
            contentEl.style.setProperty('font-size', fontSize, 'important');
            contentEl.style.setProperty('font-weight', '300', 'important');
            contentEl.style.setProperty('transition', 'none', 'important');
            contentEl.style.setProperty('-webkit-transition', 'none', 'important');
            contentEl.style.setProperty('-moz-transition', 'none', 'important');
            contentEl.style.setProperty('-o-transition', 'none', 'important');
        }

        if (type === 'video') {
            const videoId = getYouTubeVideoId(content);
            if (videoId) {
                // Store video metadata in widget element for widget awareness
                const originalUrl = content.startsWith('http') ? content : `https://www.youtube.com/watch?v=${videoId}`;
                widget.dataset.videoUrl = originalUrl;
                widget.dataset.videoId = videoId;

                const iframe = document.createElement('iframe');
                iframe.src = `https://www.youtube.com/embed/${videoId}`;
                iframe.width = '100%';
                iframe.height = '100%';
                iframe.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture";
                iframe.allowFullscreen = true;
                contentEl.appendChild(iframe);

                // Check transcript availability asynchronously
                if (typeof eel !== 'undefined' && eel.check_transcript_availability) {
                    setTimeout(() => {
                        eel.check_transcript_availability(videoId)().then(result => {
                            const indicator = widget.querySelector('.transcript-indicator');
                            if (indicator && result) {
                                // Don't overwrite if indicator is already in loading state (summarization in progress)
                                const isCurrentlyLoading = indicator.querySelector('.loading-spinner') !== null ||
                                    indicator.title === 'Generating summary...';
                                if (isCurrentlyLoading) {
                                    console.log('[Transcript Check] Skipping update - summarization in progress');
                                    return; // Don't update indicator if summarization is active
                                }

                                if (result.available) {
                                    // Document icon (transcript available)
                                    indicator.innerHTML = `
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" stroke-width="2" fill="rgba(33, 150, 243, 0.1)"/>
                                            <path d="M14 2v6h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                                            <path d="M16 13H8M16 17H8M10 9H8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                                        </svg>
                                    `;
                                    indicator.title = 'Transcript available';
                                    indicator.style.color = '#2196F3';
                                    indicator.style.opacity = '1';
                                } else {
                                    // Red X icon
                                    indicator.innerHTML = `
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="rgba(244, 67, 54, 0.2)"/>
                                            <path d="M9 9l6 6M15 9l-6 6" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
                                        </svg>
                                    `;
                                    indicator.title = 'No transcript available';
                                    indicator.style.color = '#f44336';
                                    indicator.style.opacity = '0.7';
                                }

                                // Hide the indicator after 20 seconds
                                setTimeout(() => {
                                    if (indicator && indicator.parentElement) {
                                        // Don't hide if summarization is in progress
                                        const isCurrentlyLoading = indicator.querySelector('.loading-spinner') !== null ||
                                            indicator.title === 'Generating summary...';
                                        if (isCurrentlyLoading) {
                                            return; // Don't hide if summarization is active
                                        }

                                        indicator.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                                        indicator.style.opacity = '0';
                                        indicator.style.transform = 'translateY(-50%) scale(0.8)';
                                        setTimeout(() => {
                                            if (indicator && indicator.parentElement) {
                                                indicator.remove();
                                            }
                                        }, 500); // Wait for fade-out animation
                                    }
                                }, 20000); // 20 seconds
                            }
                        }).catch(err => {
                            console.error('[Transcript Check] Error:', err);
                            const indicator = widget.querySelector('.transcript-indicator');
                            if (indicator) {
                                // Don't overwrite if indicator is already in loading state
                                const isCurrentlyLoading = indicator.querySelector('.loading-spinner') !== null ||
                                    indicator.title === 'Generating summary...';
                                if (isCurrentlyLoading) {
                                    return; // Don't update indicator if summarization is active
                                }

                                // Question mark icon
                                indicator.innerHTML = `
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="rgba(158, 158, 158, 0.2)"/>
                                        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                                    </svg>
                                `;
                                indicator.title = 'Transcript status unknown';
                                indicator.style.color = '#9E9E9E';

                                // Hide the indicator after 20 seconds even on error
                                setTimeout(() => {
                                    if (indicator && indicator.parentElement) {
                                        indicator.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                                        indicator.style.opacity = '0';
                                        indicator.style.transform = 'translateY(-50%) scale(0.8)';
                                        setTimeout(() => {
                                            if (indicator && indicator.parentElement) {
                                                indicator.remove();
                                            }
                                        }, 500); // Wait for fade-out animation
                                    }
                                }, 20000); // 20 seconds
                            }
                        });
                    }, 500); // Small delay to ensure widget is fully rendered
                }
            } else {
                console.error("Invalid YouTube video ID:", content);
            }
        } else if (type === 'image') {
            const img = document.createElement('img');
            
            // Hide image initially - only show after successful load
            img.style.opacity = '0';
            img.style.transition = 'opacity 0.3s ease';
            
            // Set a timeout to detect if image takes too long to load
            let loadTimeout;
            const timeoutDuration = 8000; // 8 seconds
            
            img.onload = () => {
                // Clear timeout if image loads successfully
                if (loadTimeout) {
                    clearTimeout(loadTimeout);
                }
                
                // Check if image actually loaded (not a broken/placeholder)
                // Broken images might trigger onload but have naturalWidth/Height of 0
                if (img.naturalWidth === 0 || img.naturalHeight === 0) {
                    console.log('Image loaded but has invalid dimensions, removing widget');
                    this.close();
                    return;
                }
                
                // Check if image is the browser's broken image placeholder
                // Broken images often have a specific size or are very small
                if (img.naturalWidth < 10 && img.naturalHeight < 10) {
                    console.log('Image appears to be a broken placeholder, removing widget');
                    this.close();
                    return;
                }
                
                // Image loaded successfully - show it
                img.style.opacity = '1';
                
                // Recalculate size when image loads
                this.autoSize();
                // Trigger layout update for all widgets, but only if no widgets are fixed
                if (window.WidgetManager && window.WidgetManager.fixedWidgets.size === 0 && !window.WidgetManager.isDragging && !window.WidgetManager.isResizing) {
                    requestAnimationFrame(() => {
                        window.WidgetManager.layoutWidgets();
                    });
                }
            };
            
            img.onerror = () => {
                // Clear timeout if error occurs
                if (loadTimeout) {
                    clearTimeout(loadTimeout);
                }
                
                console.log('Image failed to load, removing widget:', content);
                // Remove the widget if image fails to load
                this.close();
            };
            
            // Set timeout to remove widget if image takes too long
            loadTimeout = setTimeout(() => {
                console.log('Image load timeout, removing widget:', content);
                this.close();
            }, timeoutDuration);
            
            // Set src after setting up handlers
            img.src = content;
            img.crossOrigin = 'anonymous'; // Try to handle CORS
            
            contentEl.appendChild(img);
        } else if (type === 'time') {
            // Handle time widget type - display as plain text like a text widget
            try {
                let timeData = {};
                let timeFormat = '12-hour'; // Default format
                try {
                    if (content && content.trim()) {
                        timeData = JSON.parse(content);
                        // Check if format is specified in the data
                        if (timeData.format) {
                            timeFormat = timeData.format;
                        }
                    }
                } catch (e) {
                    // If parsing fails, generate from current time
                    const now = new Date();
                    const hour12 = String(now.getHours() % 12 || 12).padStart(2, '0');
                    const minute = String(now.getMinutes()).padStart(2, '0');
                    const ampm = now.getHours() >= 12 ? 'PM' : 'AM';
                    timeData = {
                        time: `${hour12}:${minute} ${ampm}`,
                        format: '12-hour'
                    };
                }
                
                // Store the format preference in the widget's dataset
                widget.dataset.timeFormat = timeFormat;
                
                // Display as plain text (like text widget) but with larger font
                // Font size is already set above when contentEl was created
                const timeText = timeData.time || (timeFormat === 'military' ? '00:00' : '00:00 AM');
                // Set text content - font size is already applied above
                contentEl.textContent = timeText;
                
                // Set up live updates (every second, client-side)
                // Use 'widget' (the element being created) instead of 'this.element' 
                // since this.element isn't set yet in the constructor
                if (!widget.dataset.updateInterval) {
                    const widgetElement = widget;
                    const updateInterval = setInterval(() => {
                        const now = new Date();
                        const storedFormat = widgetElement.dataset.timeFormat || '12-hour';
                        let timeText;
                        
                        if (storedFormat === 'military') {
                            // 24-hour format (military time)
                            const hour = String(now.getHours()).padStart(2, '0');
                            const minute = String(now.getMinutes()).padStart(2, '0');
                            timeText = `${hour}:${minute}`;
                        } else {
                            // 12-hour format with AM/PM (default)
                            const hour12 = String(now.getHours() % 12 || 12).padStart(2, '0');
                            const minute = String(now.getMinutes()).padStart(2, '0');
                            const ampm = now.getHours() >= 12 ? 'PM' : 'AM';
                            timeText = `${hour12}:${minute} ${ampm}`;
                        }
                        
                        const contentEl = widgetElement.querySelector('.widget-content');
                        if (contentEl) {
                            contentEl.textContent = timeText;
                            // Ensure font size is maintained on update with !important
                            contentEl.style.setProperty('font-size', '3em', 'important');
                            contentEl.style.setProperty('font-weight', '300', 'important');
                        }
                    }, 1000); // Update every second
                    widget.dataset.updateInterval = updateInterval;
                }
            } catch (error) {
                console.error('Error creating time widget:', error);
                // Fallback: show error message as text
                contentEl.textContent = `Error: ${error.message}`;
            }
        } else if (type === 'timer') {
            // Handle timer widget type - countdown timer
            try {
                let timerData = {};
                try {
                    if (content && content.trim()) {
                        timerData = JSON.parse(content);
                    }
                } catch (e) {
                    console.error('Error parsing timer data:', e);
                    timerData = { duration_seconds: 60 }; // Default to 60 seconds
                }
                
                const durationSeconds = timerData.duration_seconds || 60;
                const startTime = Date.now();
                
                // Store timer data in widget dataset
                widget.dataset.durationSeconds = durationSeconds;
                widget.dataset.startTime = startTime;
                
                // Format time helper function
                function formatTime(seconds) {
                    const mins = Math.floor(seconds / 60);
                    const secs = seconds % 60;
                    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
                }
                
                // Initial display
                contentEl.textContent = formatTime(durationSeconds);
                contentEl.style.setProperty('font-size', '3em', 'important');
                contentEl.style.setProperty('font-weight', '300', 'important');
                contentEl.style.setProperty('transition', 'none', 'important');
                
                // Set up countdown interval
                if (!widget.dataset.updateInterval) {
                    const widgetElement = widget;
                    const updateInterval = setInterval(() => {
                        const storedStartTime = parseInt(widgetElement.dataset.startTime) || startTime;
                        const storedDuration = parseInt(widgetElement.dataset.durationSeconds) || durationSeconds;
                        const elapsed = Math.floor((Date.now() - storedStartTime) / 1000);
                        const remaining = Math.max(0, storedDuration - elapsed);
                        
                        const contentEl = widgetElement.querySelector('.widget-content');
                        if (contentEl) {
                            if (remaining > 0) {
                                contentEl.textContent = formatTime(remaining);
                            } else {
                                contentEl.textContent = '00:00';
                                // Play alarm sound when timer reaches zero
                                if (!widgetElement.dataset.alarmPlaying) {
                                    widgetElement.dataset.alarmPlaying = 'true';
                                    try {
                                        // Create audio element and play alarm sound
                                        const alarmAudio = new Audio('alarm.mp3');
                                        alarmAudio.loop = true; // Loop until stopped
                                        alarmAudio.volume = 0.7; // Set volume to 70%
                                        
                                        // Store audio reference in widget for later cleanup
                                        widgetElement.dataset.alarmAudio = 'true';
                                        widgetElement._alarmAudio = alarmAudio;
                                        
                                        // Play the alarm
                                        alarmAudio.play().catch(err => {
                                            console.error('Error playing alarm sound:', err);
                                        });
                                        
                                        // Add visual indicator - change text color to red with opacity animation
                                        contentEl.style.color = '#ff4444';
                                        contentEl.style.animation = 'timerAlert 1.5s ease-in-out infinite';
                                    } catch (error) {
                                        console.error('Error setting up alarm sound:', error);
                                    }
                                }
                            }
                            // Ensure font size is maintained
                            contentEl.style.setProperty('font-size', '3em', 'important');
                            contentEl.style.setProperty('font-weight', '300', 'important');
                        }
                        
                        // Stop interval if timer reached zero
                        if (remaining <= 0) {
                            clearInterval(updateInterval);
                            widgetElement.dataset.updateInterval = null;
                        }
                    }, 100); // Update every 100ms for smoother countdown
                    widget.dataset.updateInterval = updateInterval;
                }
            } catch (error) {
                console.error('Error creating timer widget:', error);
                contentEl.textContent = `Error: ${error.message}`;
            }
        } else if (type === 'alarm') {
            // Handle alarm widget type - shows alarm message and plays sound immediately
            try {
                let alarmData = {};
                try {
                    if (content && content.trim()) {
                        alarmData = JSON.parse(content);
                    }
                } catch (e) {
                    console.error('Error parsing alarm data:', e);
                    // Default to current time if parsing fails
                    const now = new Date();
                    const hours = now.getHours();
                    const minutes = now.getMinutes();
                    const period = hours >= 12 ? 'PM' : 'AM';
                    const displayHour = hours === 0 ? 12 : (hours > 12 ? hours - 12 : hours);
                    alarmData = { label: `${displayHour}:${String(minutes).padStart(2, '0')} ${period}` };
                }
                
                const alarmLabel = alarmData.label || new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                const triggeredAt = Date.now();
                
                // Store alarm data in widget dataset
                widget.dataset.triggeredAt = triggeredAt;
                
                // Display alarm message
                contentEl.textContent = alarmLabel;
                contentEl.style.setProperty('font-size', '3em', 'important');
                contentEl.style.setProperty('font-weight', '300', 'important');
                contentEl.style.setProperty('transition', 'none', 'important');
                
                // Immediately play alarm sound and show visual indicator
                if (!widget.dataset.alarmPlaying) {
                    widget.dataset.alarmPlaying = 'true';
                    try {
                        // Create audio element and play alarm sound
                        const alarmAudio = new Audio('alarm.mp3');
                        alarmAudio.loop = true; // Loop until stopped
                        alarmAudio.volume = 0.7; // Set volume to 70%
                        
                        // Store audio reference in widget for later cleanup
                        widget.dataset.alarmAudio = 'true';
                        widget._alarmAudio = alarmAudio;
                        
                        // Play the alarm
                        alarmAudio.play().catch(err => {
                            console.error('Error playing alarm sound:', err);
                        });
                        
                        // Add visual indicator - change text color to red with opacity animation
                        contentEl.style.color = '#ff4444';
                        contentEl.style.animation = 'timerAlert 1.5s ease-in-out infinite';
                    } catch (error) {
                        console.error('Error setting up alarm sound:', error);
                    }
                }
            } catch (error) {
                console.error('Error creating alarm widget:', error);
                contentEl.textContent = `Error: ${error.message}`;
            }
        } else if (type === 'reminder') {
            // Handle reminder widget type - shows reminder message (no red styling, no sound)
            try {
                let reminderData = {};
                try {
                    if (content && content.trim()) {
                        reminderData = JSON.parse(content);
                    }
                } catch (e) {
                    console.error('Error parsing reminder data:', e);
                    reminderData = { label: 'Reminder' }; // Default label
                }
                
                const reminderLabel = reminderData.label || 'Reminder';
                const triggeredAt = Date.now();
                
                // Store reminder data in widget dataset
                widget.dataset.triggeredAt = triggeredAt;
                
                // Display reminder message
                contentEl.textContent = reminderLabel;
                contentEl.style.setProperty('font-size', '2.2em', 'important');
                contentEl.style.setProperty('font-weight', '300', 'important');
                contentEl.style.setProperty('transition', 'none', 'important');
                
                // Reminder widgets use normal text color (not red) - no animation, no sound
                contentEl.style.color = '#fff';
            } catch (error) {
                console.error('Error creating reminder widget:', error);
                contentEl.textContent = `Error: ${error.message}`;
            }
        } else if (type === 'weather') {
            // Handle weather widget type
            const weatherData = JSON.parse(content);
            console.log("Weather data received:", weatherData); // Debug log

            // Helper to map weather conditions from Python to an SVG icon
            function getWeatherIconSVG(condition, weatherData) {
                // Check if it's night time
                const isNight = () => {
                    if (!weatherData.sunrise || !weatherData.sunset || !weatherData.timestamp) {
                        return false; // Default to day if we don't have time data
                    }

                    const currentTime = weatherData.timestamp * 1000; // Convert to milliseconds
                    const sunriseTime = weatherData.sunrise * 1000;
                    const sunsetTime = weatherData.sunset * 1000;

                    // It's night if current time is after sunset or before sunrise
                    return currentTime < sunriseTime || currentTime > sunsetTime;
                };

                const nightTime = isNight();

                const icons = {
                    'Clouds': `<svg viewBox="0 0 64 64" stroke-width="3" stroke="#94dfff" fill="none"><path d="M41.4 20.7A14.4 14.4 0 0 0 14.2 23a12.3 12.3 0 0 0-2.2 24.2h31.7a10.8 10.8 0 0 0 7.7-18.8 14.3 14.3 0 0 0-10-7.7z"/></svg>`,
                    'Rain': `<svg viewBox="0 0 64 64" stroke-width="3" stroke="#94dfff" fill="none"><path d="M41.4 20.7A14.4 14.4 0 0 0 14.2 23a12.3 12.3 0 0 0-2.2 24.2h31.7a10.8 10.8 0 0 0 7.7-18.8 14.3 14.3 0 0 0-10-7.7z"/><path d="M24.5 50v8M32.5 50v8M28.5 54v8" stroke-linecap="round" stroke-width="2"/></svg>`,
                    'Clear': nightTime ?
                        `<svg viewBox="0 0 64 64" stroke-width="2" stroke="#fff" fill="none">
                            <circle cx="20" cy="15" r="1" fill="#fff"/>
                            <circle cx="45" cy="25" r="1" fill="#fff"/>
                            <circle cx="15" cy="35" r="1" fill="#fff"/>
                            <circle cx="50" cy="45" r="1" fill="#fff"/>
                            <circle cx="25" cy="50" r="1" fill="#fff"/>
                            <circle cx="40" cy="15" r="1" fill="#fff"/>
                            <circle cx="10" cy="20" r="1" fill="#fff"/>
                            <circle cx="55" cy="35" r="1" fill="#fff"/>
                        </svg>` :
                        `<svg viewBox="0 0 64 64" stroke-width="3" stroke="#ffe680" fill="none"><path d="M32 20.5a11.5 11.5 0 1 1-11.5 11.5A11.5 11.5 0 0 1 32 20.5m0-5v-6M45.9 18.1l4.2-4.2M52.5 32h6M45.9 45.9l4.2 4.2M32 52.5v6M18.1 45.9l-4.2 4.2M11.5 32h-6M18.1 18.1l-4.2-4.2" stroke-linecap="round"/></svg>`,
                    'Snow': `<svg viewBox="0 0 64 64" stroke-width="3" stroke="#fff" fill="none"><path d="M41.4 20.7A14.4 14.4 0 0 0 14.2 23a12.3 12.3 0 0 0-2.2 24.2h31.7a10.8 10.8 0 0 0 7.7-18.8 14.3 14.3 0 0 0-10-7.7z"/><path d="m24.5 50-3 3 3 3m3-6 3 3-3 3m5 0-3 3 3 3m3-6 3 3-3 3" stroke-linecap="round" stroke-width="2"/></svg>`,
                    'Drizzle': `<svg viewBox="0 0 64 64" stroke-width="3" stroke="#94dfff" fill="none"><path d="M41.4 20.7A14.4 14.4 0 0 0 14.2 23a12.3 12.3 0 0 0-2.2 24.2h31.7a10.8 10.8 0 0 0 7.7-18.8 14.3 14.3 0 0 0-10-7.7z"/><path d="M28.5 50v6M35.5 50v6" stroke-linecap="round" stroke-width="2"/></svg>`,
                    'Thunderstorm': `<svg viewBox="0 0 64 64" stroke-width="3" stroke="#ffeb3b" fill="none"><path d="M41.4 20.7A14.4 14.4 0 0 0 14.2 23a12.3 12.3 0 0 0-2.2 24.2h31.7a10.8 10.8 0 0 0 7.7-18.8 14.3 14.3 0 0 0-10-7.7z" stroke="#94dfff"/><path d="m30 48-4 7h12l-4 7" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
                    'default': `<svg viewBox="0 0 64 64" stroke-width="3" stroke="#94dfff" fill="none"><path d="M41.4 20.7A14.4 14.4 0 0 0 14.2 23a12.3 12.3 0 0 0-2.2 24.2h31.7a10.8 10.8 0 0 0 7.7-18.8 14.3 14.3 0 0 0-10-7.7z"/></svg>`
                };
                return icons[condition] || icons['default'];
            }

            // Determine main weather condition from description
            const mainCondition = weatherData.description ?
                weatherData.description.split(' ')[0] : 'default';

            // The entire widget's HTML structure is built here
            const weatherWidgetHTML = `
                <div class="weather-container">
                    
                    <div class="weather-main">
                        <div class="weather-temp-section">
                            <div class="weather-temperature">${Math.round(weatherData.temp)}${weatherData.temp_unit || '°C'}</div>
                            <div class="weather-location">${weatherData.location || 'Unknown'}</div>
                            <div class="weather-description">${weatherData.description || ''}</div>
                        </div>
                        <div class="weather-icon-section">
                            ${getWeatherIconSVG(mainCondition, weatherData)}
                        </div>
                    </div>
                </div>
            `;
            contentEl.innerHTML = weatherWidgetHTML;
        } else if (type === 'calculator') {
            // Handle calculator widget type - create iframe with Desmos scientific calculator
            const iframe = document.createElement('iframe');
            iframe.src = content || 'https://www.desmos.com/scientific';
            iframe.style.width = '100%';
            iframe.style.height = '100%';
            iframe.style.border = 'none';
            iframe.style.display = 'block';
            iframe.style.position = 'absolute';
            iframe.style.top = '0';
            iframe.style.left = '0';
            iframe.allow = "fullscreen";
            iframe.allowFullscreen = true;
            // Ensure content area fills the widget
            contentEl.style.position = 'relative';
            contentEl.style.width = '100%';
            contentEl.style.height = '100%';
            contentEl.style.padding = '0';
            contentEl.style.margin = '0';
            contentEl.appendChild(iframe);
        } else if (type === 'notes') {
            // Handle notes widget type - create editable textarea
            const textarea = document.createElement('textarea');
            try {
                // Set content with error handling for very long data URLs
                const contentToSet = content || '';
                // Check if content is extremely long (might be a data URL issue)
                if (contentToSet.length > 2000000) {
                    console.warn('[Widget] Notes content too long, truncating to prevent errors');
                    textarea.value = contentToSet.substring(0, 1000000) + '\n\n[Content truncated - too large]';
                } else {
                    textarea.value = contentToSet;
                }
            } catch (e) {
                console.error('[Widget] Error setting notes content:', e);
                textarea.value = '[Error loading notes content - data may be corrupted]';
            }
            textarea.style.width = '100%';
            textarea.style.height = '100%';
            textarea.style.border = 'none';
            textarea.style.background = 'transparent';
            textarea.style.color = 'inherit';
            textarea.style.fontFamily = 'inherit';
            textarea.style.fontSize = '1em';
            textarea.style.padding = '10px';
            textarea.style.resize = 'none';
            textarea.style.outline = 'none';
            textarea.placeholder = 'Start typing your notes here...';
            textarea.style.boxSizing = 'border-box';
            textarea.style.lineHeight = '1.5';
            // Prevent textarea from interfering with widget dragging
            textarea.addEventListener('mousedown', (e) => {
                e.stopPropagation();
            });
            // Make textarea fill the content area
            contentEl.style.padding = '0';
            contentEl.style.overflow = 'hidden';
            contentEl.appendChild(textarea);
        } else if (type === 'gesture_control') {
            // Handle gesture control widget type - create toggle switch
            contentEl.style.padding = '20px';
            contentEl.style.display = 'flex';
            contentEl.style.flexDirection = 'column';
            contentEl.style.alignItems = 'center';
            contentEl.style.justifyContent = 'center';
            contentEl.style.gap = '15px';
            
            // Status label
            const statusLabel = document.createElement('div');
            statusLabel.id = `gesture-status-${id}`;
            statusLabel.textContent = 'Status: OFF';
            statusLabel.style.fontSize = '14px';
            statusLabel.style.color = '#ffffff';
            statusLabel.style.marginBottom = '10px';
            
            // Toggle switch container
            const switchContainer = document.createElement('div');
            switchContainer.style.display = 'flex';
            switchContainer.style.alignItems = 'center';
            switchContainer.style.gap = '15px';
            
            // Toggle switch
            const toggleSwitch = document.createElement('label');
            toggleSwitch.style.position = 'relative';
            toggleSwitch.style.display = 'inline-block';
            toggleSwitch.style.width = '60px';
            toggleSwitch.style.height = '34px';
            
            const slider = document.createElement('input');
            slider.type = 'checkbox';
            slider.id = `gesture-toggle-${id}`;
            slider.style.opacity = '0';
            slider.style.width = '0';
            slider.style.height = '0';
            
            const sliderSpan = document.createElement('span');
            sliderSpan.style.position = 'absolute';
            sliderSpan.style.cursor = 'pointer';
            sliderSpan.style.top = '0';
            sliderSpan.style.left = '0';
            sliderSpan.style.right = '0';
            sliderSpan.style.bottom = '0';
            sliderSpan.style.backgroundColor = '#ccc';
            sliderSpan.style.transition = '.4s';
            sliderSpan.style.borderRadius = '34px';
            
            const sliderBefore = document.createElement('span');
            sliderBefore.style.position = 'absolute';
            sliderBefore.style.content = '""';
            sliderBefore.style.height = '26px';
            sliderBefore.style.width = '26px';
            sliderBefore.style.left = '4px';
            sliderBefore.style.bottom = '4px';
            sliderBefore.style.backgroundColor = 'white';
            sliderBefore.style.transition = '.4s';
            sliderBefore.style.borderRadius = '50%';
            
            sliderSpan.appendChild(sliderBefore);
            toggleSwitch.appendChild(slider);
            toggleSwitch.appendChild(sliderSpan);
            
            // Toggle switch label
            const switchLabel = document.createElement('span');
            switchLabel.id = `gesture-label-${id}`;
            switchLabel.textContent = 'OFF';
            switchLabel.style.fontSize = '16px';
            switchLabel.style.fontWeight = 'bold';
            switchLabel.style.color = '#ffffff';
            
            switchContainer.appendChild(toggleSwitch);
            switchContainer.appendChild(switchLabel);
            
            // Instructions
            const instructions = document.createElement('div');
            instructions.style.fontSize = '11px';
            instructions.style.color = '#999';
            instructions.style.textAlign = 'center';
            instructions.style.lineHeight = '1.4';
            instructions.innerHTML = 'Use index finger to move cursor<br>Pinch thumb-index for left click<br>Pinch thumb-middle for right click';
            
            contentEl.appendChild(statusLabel);
            contentEl.appendChild(switchContainer);
            contentEl.appendChild(instructions);
            
            // Toggle functionality
            slider.addEventListener('change', async function() {
                try {
                    const result = await eel.toggle_gesture_control()();
                    if (result.status === 'on') {
                        statusLabel.textContent = 'Status: ON';
                        statusLabel.style.color = '#44ff44';
                        switchLabel.textContent = 'ON';
                        switchLabel.style.color = '#44ff44';
                        slider.checked = true;
                        sliderSpan.style.backgroundColor = '#44ff44';
                    } else if (result.status === 'off') {
                        statusLabel.textContent = 'Status: OFF';
                        statusLabel.style.color = '#ffffff';
                        switchLabel.textContent = 'OFF';
                        switchLabel.style.color = '#ffffff';
                        slider.checked = false;
                        sliderSpan.style.backgroundColor = '#ccc';
                    } else {
                        statusLabel.textContent = 'Status: ERROR';
                        statusLabel.style.color = '#ff4444';
                        alert(result.message || 'Error toggling gesture control');
                        slider.checked = false;
                        sliderSpan.style.backgroundColor = '#ccc';
                    }
                } catch (error) {
                    console.error('Error toggling gesture control:', error);
                    statusLabel.textContent = 'Status: ERROR';
                    statusLabel.style.color = '#ff4444';
                    slider.checked = false;
                    sliderSpan.style.backgroundColor = '#ccc';
                }
            });
            
            // Update slider visual state
            slider.addEventListener('change', function() {
                if (slider.checked) {
                    sliderBefore.style.transform = 'translateX(26px)';
                } else {
                    sliderBefore.style.transform = 'translateX(0)';
                }
            });
            
            // Check status periodically
            setInterval(async function() {
                try {
                    const status = await eel.get_gesture_control_status()();
                    if (status.active) {
                        if (!slider.checked) {
                            slider.checked = true;
                            statusLabel.textContent = 'Status: ON';
                            statusLabel.style.color = '#44ff44';
                            switchLabel.textContent = 'ON';
                            switchLabel.style.color = '#44ff44';
                            sliderSpan.style.backgroundColor = '#44ff44';
                            sliderBefore.style.transform = 'translateX(26px)';
                        }
                    } else {
                        if (slider.checked) {
                            slider.checked = false;
                            statusLabel.textContent = 'Status: OFF';
                            statusLabel.style.color = '#ffffff';
                            switchLabel.textContent = 'OFF';
                            switchLabel.style.color = '#ffffff';
                            sliderSpan.style.backgroundColor = '#ccc';
                            sliderBefore.style.transform = 'translateX(0)';
                        }
                    }
                } catch (error) {
                    console.error('Error checking gesture control status:', error);
                }
            }, 1000);
        } else {
            contentEl.textContent = content;
        }

        const resizeHandle = document.createElement('div');
        resizeHandle.className = 'widget-resize';

        widget.appendChild(header);
        widget.appendChild(contentEl);
        widget.appendChild(resizeHandle);

        return widget;
    }

    // New method to handle right-click to close (only on title)
    setupRightClickClose() {
        const titleEl = this.element.querySelector('.widget-title');
        if (titleEl) {
            titleEl.addEventListener('contextmenu', (e) => {
            e.preventDefault(); // Prevent default context menu
                e.stopPropagation(); // Stop event from bubbling to widget content
            this.close();
        });
        }
    }

    setupClickToFocus() {
        // Add click handler to focus widget when clicked (if unfocused)
        this.element.addEventListener('click', (e) => {
            // Don't focus if clicking on close button, resize handle, or if already dragging
            if (e.target.classList.contains('widget-close') ||
                e.target.classList.contains('widget-resize') ||
                this.element.classList.contains('dragging')) {
                return;
            }

            // Only focus if widget is currently unfocused
            if (this.element.classList.contains('widget-unfocused') && this.groupId) {
                // Add to focused set without unfocusing others
                if (window.WidgetManager) {
                    window.WidgetManager.setFocus(this.groupId, true); // true = add to focused, don't replace
                }
            }
        });
    }

    autoSize() {
        const content = this.element.querySelector('.widget-content');
        const type = content.classList.contains('video') ? 'video' :
            content.classList.contains('image') ? 'image' :
                content.classList.contains('weather') ? 'weather' :
                    content.classList.contains('time') ? 'time' :
                        content.classList.contains('notes') ? 'notes' : 'text';
        
        // Skip auto-sizing for time widgets - they have fixed large font size
        if (type === 'time') {
            return;
        }
        
        // Set default size for notes widgets
        if (type === 'notes') {
            const width = Math.min(400, window.innerWidth * 0.4);
            const height = Math.min(300, window.innerHeight * 0.4);
            this.setSize(width + 30, height + 60);
            return;
        }

        // Get context about other widgets for intelligent sizing
        const totalWidgets = window.WidgetManager ? window.WidgetManager.widgets.length : 1;
        const imageWidgets = window.WidgetManager ?
            window.WidgetManager.widgets.filter(w => {
                const c = w.element.querySelector('.widget-content');
                return c && c.classList.contains('image');
            }).length : 0;
        const textWidgets = window.WidgetManager ?
            window.WidgetManager.widgets.filter(w => {
                const c = w.element.querySelector('.widget-content');
                return c && c.classList.contains('text');
            }).length : 0;

        const isSearchResult = this.element.querySelector('.widget-title').textContent.includes("SEARCH") ||
            this.element.querySelector('.widget-title').textContent.includes("KNOWLEDGE");

        // Calculate available space intelligently
        const jarvis = document.querySelector('.jarvis-container');
        const winW = window.innerWidth;
        const winH = window.innerHeight;
        let availableWidth = winW;
        let availableHeight = winH;

        if (jarvis) {
            const jarvisRect = jarvis.getBoundingClientRect();
            // Consider space around Jarvis
            const rightSpace = winW - jarvisRect.right;
            const leftSpace = jarvisRect.left;
            availableWidth = Math.max(rightSpace, leftSpace) * 0.9; // Use 90% of best side
            availableHeight = winH * 0.85; // Leave some margin
        }

        if (type === 'video') {
            // Set default size for video widgets
            const width = Math.min(560, window.innerWidth * 0.8);
            const height = (width * 9) / 16; // 16:9 aspect ratio
            this.setSize(width + 30, height + 60);
        } else if (type === 'image') {
            // If custom dimensions are provided, use them as base but may adjust
            let baseWidth, baseHeight;
            if (this.customWidth && this.customHeight) {
                baseWidth = this.customWidth;
                baseHeight = this.customHeight;
            } else {
                const img = content.querySelector('img');
                if (img && img.naturalWidth && img.naturalHeight) {
                    const ratio = img.naturalWidth / img.naturalHeight;
                    baseWidth = img.naturalWidth;
                    baseHeight = img.naturalHeight;
                } else {
                    // Fallback if image hasn't loaded yet
                    baseWidth = 300;
                    baseHeight = 200;
                }
            }

            const ratio = baseWidth / baseHeight;
            let width, height;

            // Intelligent sizing based on context
            if (isSearchResult || imageWidgets > 1) {
                // When multiple images or search results, make them smaller to fit nicely
                // Calculate optimal size based on available space and number of images
                const maxImagesPerRow = Math.floor(availableWidth / 250); // Assume ~250px per image
                const imagesPerRow = Math.min(imageWidgets, maxImagesPerRow);
                const rows = Math.ceil(imageWidgets / Math.max(1, imagesPerRow));

                // Size images to fit nicely in grid
                const maxWidth = Math.min(
                    availableWidth / Math.max(1, imagesPerRow) - 20, // Account for spacing
                    350, // Max width per image
                    baseWidth
                );
                width = Math.max(200, maxWidth); // Min 200px
                height = width / ratio;

                // Ensure height doesn't exceed available space
                const maxHeight = (availableHeight / Math.max(1, rows)) - 20;
                if (height > maxHeight) {
                    height = maxHeight;
                    width = height * ratio;
                }
            } else {
                // Single image - can be larger but still respect limits
                width = Math.min(400, baseWidth, availableWidth * 0.6);
                height = width / ratio;

                if (height > availableHeight * 0.7) {
                    height = availableHeight * 0.7;
                    width = height * ratio;
                }
            }

            this.setSize(width + 20, height + 40); // Add padding for widget chrome
        } else if (type === 'weather') {
            // Set fixed size for weather widgets
            const width = 320;
            const height = 230;
            this.setSize(width, height);
        } else if (type === 'time') {
            // Size time widget like a text widget (auto-size based on content)
            // No fixed size - let it auto-size like text widgets
        } else { // Text widget
            const text = content.textContent;
            const length = text.length;

            // Calculate font size based on text length
            let fontSize;
            if (length > 200) {
                fontSize = '1.1em';
            } else if (length > 100) {
                fontSize = '1.6em';
            } else if (length > 50) {
                fontSize = '1.8em';
            } else {
                fontSize = '2em';
            }
            content.style.fontSize = fontSize;

            // Calculate content dimensions using a temporary element with proper styling
            // First, measure content without width constraints to get natural width
            const calculator = document.createElement('div');
            calculator.className = 'size-calculator';
            calculator.style.width = 'auto';
            calculator.style.maxWidth = 'none';
            calculator.style.fontSize = fontSize;
            calculator.style.fontFamily = window.getComputedStyle(content).fontFamily;
            calculator.style.lineHeight = window.getComputedStyle(content).lineHeight || '1.4';
            calculator.style.whiteSpace = 'pre-wrap';
            calculator.style.wordWrap = 'break-word';
            calculator.style.padding = '0';
            calculator.style.margin = '0';
            calculator.style.position = 'absolute';
            calculator.style.visibility = 'hidden';
            calculator.style.left = '-9999px'; // Move off-screen
            calculator.textContent = text;
            document.body.appendChild(calculator);

            // Force a reflow to ensure accurate measurement
            calculator.offsetWidth;

            // Get actual content dimensions (natural width)
            // Use scrollWidth for more accurate width measurement (accounts for any overflow)
            const contentWidth = Math.max(calculator.offsetWidth, calculator.scrollWidth);
            const contentHeight = calculator.offsetHeight;

            // Calculate widget dimensions
            // Widget has 15px padding on each side (30px total)
            // Title has 12px padding on each side (inside widget)
            // Content has 12px padding on each side (inside widget) - matches title
            // From widget edge: Both title and content text = 15px + 12px = 27px each side
            const headerHeight = this.element.querySelector('.widget-header').offsetHeight || 60;
            const widgetPadding = 30; // 15px left + 15px right
            const contentPadding = 24; // 12px left + 12px right (matches title padding)
            const widgetVerticalPadding = 30; // 15px top + 15px bottom
            const contentVerticalPadding = 24; // 12px top + 12px bottom

            // Calculate width requirements for both title and content
            // Both now use the same spacing: 15px widget + 12px internal = 27px each side
            const titleElement = this.element.querySelector('.widget-title');

            // Content needs: text width + widget padding (15px each) + content padding (12px each)
            // Add buffer to account for:
            // - Rendering differences between browsers
            // - Unfocused state (widget scales to 0.75 but font size also changes)
            // - Text wrapping edge cases
            let requiredWidthForContent = contentWidth + widgetPadding + contentPadding + 15;

            // Title: scrollWidth already includes title's 12px padding, just add widget padding
            // Add buffer to ensure title doesn't get cut off in focused or unfocused states
            let requiredWidthForTitle = 0;
            if (titleElement) {
                // Force a reflow to ensure scrollWidth is accurate
                titleElement.offsetWidth;
                // Ensure width works in both focused (normal) and unfocused (scaled 0.75 + smaller font) states
                requiredWidthForTitle = titleElement.scrollWidth + widgetPadding + 15;
            }

            // Use whichever requires more width
            // Both title and content now have equal 27px spacing on each side (15px widget + 12px internal)
            // The extra 15px buffer ensures content doesn't get clipped in focused or unfocused states
            let width = Math.max(requiredWidthForContent, requiredWidthForTitle);

            // Calculate height with extra bottom padding for better spacing
            // Add extra bottom padding to prevent content from being too close to bottom edge
            const extraBottomPadding = 19; // Additional space at the bottom
            let height = contentHeight + headerHeight + widgetVerticalPadding + contentVerticalPadding + extraBottomPadding;

            // Ensure minimum dimensions for very small content
            width = Math.max(width, 200);
            height = Math.max(height, 120);

            // Cap maximum width to prevent extremely wide widgets
            const maxWidth = Math.min(availableWidth * 0.8, 700);
            width = Math.min(width, maxWidth);

            // The height above was measured at the text's natural, unwrapped
            // width. If the cap just narrowed the widget, the text now wraps
            // onto more lines than that measurement assumed, and the widget is
            // too short for its own contents - anything long gets clipped
            // mid-sentence. Re-measure at the width we actually settled on.
            const finalContentWidth = width - widgetPadding - contentPadding;
            if (finalContentWidth < contentWidth) {
                calculator.style.width = finalContentWidth + 'px';
                calculator.style.maxWidth = finalContentWidth + 'px';
                calculator.offsetWidth; // force a reflow before re-reading
                height = calculator.offsetHeight + headerHeight +
                    widgetVerticalPadding + contentVerticalPadding + extraBottomPadding;
                height = Math.max(height, 120);
            }

            // Don't cap height too aggressively - let it grow to fit content
            // Only cap if it would go way off screen
            const maxReasonableHeight = availableHeight * 0.9;
            if (height > maxReasonableHeight) {
                // If content is too tall, allow scrolling but set reasonable max
                height = maxReasonableHeight;
            }

            document.body.removeChild(calculator);
            this.setSize(width, height);
        }
    }

    setPosition(x, y, immediate = false) {
        const maxX = window.innerWidth - this.element.offsetWidth;
        const maxY = window.innerHeight - this.element.offsetHeight;

        // Ensure widget stays within window bounds
        x = Math.max(0, Math.min(x, maxX));
        y = Math.max(0, Math.min(y, maxY));

        // If dragging, always use immediate positioning (no transitions)
        const isCurrentlyDragging = this.element.classList.contains('dragging');

        if (immediate || isCurrentlyDragging) {
            this.element.style.transition = 'none';
            this.element.style.left = `${x}px`;
            this.element.style.top = `${y}px`;
            if (!isCurrentlyDragging) {
                requestAnimationFrame(() => {
                    this.element.style.transition = '';
                });
            }
        } else {
            this.element.style.left = `${x}px`;
            this.element.style.top = `${y}px`;
        }
    }

    setSize(width, height) {
        width = Math.max(200, Math.min(width, window.innerWidth * 0.9));
        height = Math.max(100, Math.min(height, window.innerHeight * 0.9));

        this.element.style.width = `${width}px`;
        this.element.style.height = `${height}px`;
    }

    setupDragging() {
        let isDragging = false;
        let currentX;
        let currentY;
        let initialX;
        let initialY;

        const header = this.element.querySelector('.widget-header');

        const startDragging = (e) => {
            if (e.target.classList.contains('widget-close') ||
                e.target.classList.contains('widget-resize')) {
                return;
            }

            isDragging = true;
            this.element.classList.add('dragging');

            // Bring widget to front by setting highest z-index
            const currentHighest = getCurrentHighestWidgetZIndex();
            const newZIndex = currentHighest + 1;
            // Use setProperty with important flag to override CSS !important rules
            this.element.style.setProperty('z-index', newZIndex, 'important');
            // Update global tracker
            if (newZIndex > highestWidgetZIndex) {
                highestWidgetZIndex = newZIndex;
            }
            // Store the z-index on the element for persistence
            this.element.dataset.widgetZIndex = newZIndex;

            // Unfix the widget when user starts dragging it again
            // This allows the user to reposition it
            if (window.WidgetManager) {
                window.WidgetManager.fixedWidgets.delete(this);
                window.WidgetManager.startDragging(this);
                // Temporarily focus this widget while dragging (user action, so add to focused)
                if (this.groupId) {
                    window.WidgetManager.setFocus(this.groupId, true); // true = add to focused, don't unfocus others
                }
            }

            initialX = e.clientX - this.element.offsetLeft;
            initialY = e.clientY - this.element.offsetTop;
        };

        const drag = (e) => {
            if (isDragging) {
                e.preventDefault();
                currentX = e.clientX - initialX;
                currentY = e.clientY - initialY;

                // Call setPosition to handle boundary checks during drag
                this.setPosition(currentX, currentY);


            }
        };

        const stopDragging = () => {
            if (isDragging) {
                isDragging = false;
                this.element.classList.remove('dragging');

                // Keep the z-index that was set during dragging
                // This ensures the widget stays on top after dragging
                const savedZIndex = this.element.dataset.widgetZIndex;
                if (savedZIndex) {
                    // Use setProperty with important flag to override CSS !important rules
                    this.element.style.setProperty('z-index', savedZIndex, 'important');
                }

                // Notify WidgetManager that dragging has stopped
                if (window.WidgetManager) {
                    window.WidgetManager.stopDragging();
                }
            }
        };

        header.addEventListener('mousedown', startDragging);
        document.addEventListener('mousemove', drag);
        document.addEventListener('mouseup', stopDragging);
    }

    setupResizing() {
        const resizeHandle = this.element.querySelector('.widget-resize');
        let isResizing = false;
        let initialWidth;
        let initialHeight;
        let initialX;
        let initialY;

        const startResizing = (e) => {
            isResizing = true;
            this.element.classList.add('resizing');

            // Unfix the widget when user starts resizing it again
            // This allows the user to resize it
            if (window.WidgetManager) {
                window.WidgetManager.fixedWidgets.delete(this);
                window.WidgetManager.startResizing(this);
            }

            initialWidth = this.element.offsetWidth;
            initialHeight = this.element.offsetHeight;
            initialX = e.clientX;
            initialY = e.clientY;
            e.preventDefault();
        };

        const resize = (e) => {
            if (isResizing) {
                e.preventDefault();
                const width = initialWidth + (e.clientX - initialX);
                const height = initialHeight + (e.clientY - initialY);
                this.setSize(width, height);
            }
        };

        const stopResizing = () => {
            if (isResizing) {
                isResizing = false;
                this.element.classList.remove('resizing');

                // Notify WidgetManager that resizing has stopped
                if (window.WidgetManager) {
                    window.WidgetManager.stopResizing();
                }
            }
        };

        resizeHandle.addEventListener('mousedown', startResizing);
        document.addEventListener('mousemove', resize);
        document.addEventListener('mouseup', stopResizing);
    }

    close() {
        // Clear any update intervals before closing
        if (this.element.dataset.updateInterval) {
            clearInterval(parseInt(this.element.dataset.updateInterval));
            delete this.element.dataset.updateInterval;
        }
        
        // Stop alarm audio if playing
        if (this.element._alarmAudio) {
            try {
                this.element._alarmAudio.pause();
                this.element._alarmAudio.currentTime = 0;
                this.element._alarmAudio = null;
            } catch (error) {
                console.error('Error stopping alarm audio:', error);
            }
        }
        
        // animate out then remove and inform manager
        this.element.classList.add('exiting');
        this.element.classList.remove('active');
        setTimeout(() => {
            if (this.element && this.element.parentNode) this.element.remove();
            if (window.WidgetManager) window.WidgetManager.unregister(this);
        }, 200); // Match the CSS transition duration
    }
}
// createWidget('widget-1', 'Widget 1', 'text', 'Hello, world!');

// Handle the input field expansion and submission
const textInputContainer = document.getElementById('text-input-container');
const textInput = document.getElementById('text-input');

// Enhanced Widget layout manager with smooth animations and better positioning
window.WidgetManager = {
    widgets: [],
    spacing: 20,
    margin: 16,
    staggerDelay: 80,
    currentFocusedGroupId: null, // Track which group is currently focused (for backward compatibility)
    focusedGroupIds: new Set(), // Track multiple focused groups (user-clicked widgets)
    isDragging: false, // Track if any widget is currently being dragged
    draggedWidget: null, // Track which widget is being dragged
    isResizing: false, // Track if any widget is currently being resized
    resizedWidget: null, // Track which widget is being resized
    fixedWidgets: new Set(), // Track widgets that should maintain their positions

    register(widget) {
        this.widgets.push(widget);
        document.body.classList.add('widgets-active');

        // Automatically focus the newly registered widget's group (automatic focus, not user click)
        if (widget.groupId) {
            this.setFocus(widget.groupId, false); // false = automatic focus, may unfocus others
        }

        // Check if widget has images that need to load
        const content = widget.element.querySelector('.widget-content');
        const isImageWidget = content && content.classList.contains('image');

        if (isImageWidget) {
            const img = content.querySelector('img');
            if (img && !img.complete) {
                // Wait for image to load before final layout
                img.addEventListener('load', () => {
                    // Only layout if no widgets are fixed
                    if (this.fixedWidgets.size === 0 && !this.isDragging && !this.isResizing) {
                        requestAnimationFrame(() => {
                            setTimeout(() => {
                                this.layoutWidgets();
                            }, 100);
                        });
                    }
                }, { once: true });
            }
        }

        // Initial layout (will be refined when images load)
        // Only layout if no widgets are fixed (new widgets can still layout initially)
        if (this.fixedWidgets.size === 0 && !this.isDragging && !this.isResizing) {
            requestAnimationFrame(() => {
                setTimeout(() => {
                    this.layoutWidgets();
                }, isImageWidget ? 150 : 50);
            });
        }
    },

    unregister(widget) {
        this.widgets = this.widgets.filter(w => w !== widget);

        // Remove from fixed set if it was there
        this.fixedWidgets.delete(widget);

        // If it was being dragged, clear drag state
        if (this.draggedWidget === widget) {
            this.isDragging = false;
            this.draggedWidget = null;
        }

        // If it was being resized, clear resize state
        if (this.resizedWidget === widget) {
            this.isResizing = false;
            this.resizedWidget = null;
        }

        // Update focus states after removal
        this.updateWidgetFocus();

        // Re-layout remaining widgets smoothly, but only if no widgets are fixed
        if (this.fixedWidgets.size === 0 && !this.isDragging && !this.isResizing) {
            requestAnimationFrame(() => {
                setTimeout(() => {
                    this.layoutWidgets();
                }, 100);
            });
        }

        if (this.widgets.length === 0) {
            // Delay removing the class to allow exit animations
            setTimeout(() => {
                document.body.classList.remove('widgets-active');
                this.currentFocusedGroupId = null;
                this.fixedWidgets.clear(); // Clear fixed widgets when all are gone
            }, 500);
        }
    },

    clearAll() {
        this.widgets.slice().forEach(w => w.close());
    },

    setFocus(groupId, addToFocused = false) {
        // If addToFocused is true, add to focused set (user clicked)
        // If false, replace focused set (automatic focus)
        if (addToFocused) {
            // Add to focused set - don't unfocus others
            this.focusedGroupIds.add(groupId);
            this.currentFocusedGroupId = groupId; // Keep for backward compatibility
        } else {
            // Replace focused set - automatic focus (new widget created)
            // Only auto-focus if there are 3+ widgets, otherwise clear focused set
            const totalWidgets = this.widgets.length;
            if (totalWidgets >= 3) {
                // Auto-focus: clear user-focused widgets and focus only the new one
                this.focusedGroupIds.clear();
                this.focusedGroupIds.add(groupId);
                this.currentFocusedGroupId = groupId;
            } else {
                // Few widgets: clear focus (all widgets stay normal size)
                this.focusedGroupIds.clear();
                this.currentFocusedGroupId = null;
            }
        }

        // Update all widgets' focus state
        this.updateWidgetFocus();
    },

    updateWidgetFocus(skipLayout = false) {
        const totalWidgets = this.widgets.length;
        const shouldShrinkUnfocused = totalWidgets >= 3; // Only shrink when 3+ widgets

        this.widgets.forEach(widget => {
            if (!widget.element) return;

            // Check if widget's group is in the focused set
            const isFocused = widget.groupId && this.focusedGroupIds.has(widget.groupId);

            if (shouldShrinkUnfocused) {
                if (isFocused) {
                    widget.element.classList.add('widget-focused');
                    widget.element.classList.remove('widget-unfocused');
                } else {
                    widget.element.classList.add('widget-unfocused');
                    widget.element.classList.remove('widget-focused');
                }
            } else {
                // When few widgets, all are normal size
                widget.element.classList.remove('widget-focused', 'widget-unfocused');
            }
        });

        // Re-layout after focus change (unless explicitly skipped to avoid loops)
        if (!skipLayout) {
            requestAnimationFrame(() => {
                this.layoutWidgets();
            });
        }
    },

    getStaggerDelay(widget) {
        const index = this.widgets.indexOf(widget);
        return index >= 0 ? index * this.staggerDelay : 0;
    },

    layoutWidgets() {
        // Don't layout if a widget is being dragged - let the user control it
        if (this.isDragging && this.draggedWidget) {
            return;
        }

        // Don't layout if a widget is being resized - let the user control it
        if (this.isResizing && this.resizedWidget) {
            return;
        }

        // Don't layout if there are any fixed widgets - they were recently dragged/resized
        // This prevents other widgets from moving when a widget was just positioned
        if (this.fixedWidgets.size > 0) {
            return;
        }

        const jarvis = document.querySelector('.jarvis-container');
        const winW = window.innerWidth;
        const winH = window.innerHeight;
        const spacing = this.spacing;
        const margin = this.margin;

        // Intelligent sizing: calculate sizes considering all widgets
        this.widgets.forEach(w => {
            if (typeof w.autoSize === 'function') {
                w.autoSize();
            }
        });

        // Force a reflow to ensure sizes are calculated
        this.widgets.forEach(w => {
            if (w.element) {
                w.element.offsetHeight; // Force layout recalculation
            }
        });

        // Get Jarvis position
        let jarvisRect = {
            left: winW / 2 - 110,
            right: winW / 2 + 110,
            top: 100,
            bottom: 320,
            centerX: winW / 2,
            centerY: 210,
            radius: 150 // Safe radius around Jarvis
        };

        if (jarvis) {
            const rect = jarvis.getBoundingClientRect();
            jarvisRect = {
                left: rect.left,
                right: rect.right,
                top: rect.top,
                bottom: rect.bottom,
                centerX: rect.left + rect.width / 2,
                centerY: rect.top + rect.height / 2,
                radius: Math.max(rect.width, rect.height) / 2 + spacing + 50
            };
        }

        // Collect all widget data for intelligent layout
        // Include all widgets, but mark fixed ones (recently dragged) as non-movable
        const widgetData = this.widgets
            .filter(w => w.element) // Only widgets with elements
            .map(w => {
                const rect = w.element.getBoundingClientRect();
                const isFixed = this.fixedWidgets.has(w) || w === this.draggedWidget;
                return {
                    widget: w,
                    x: rect.left,
                    y: rect.top,
                    width: rect.width || w.customWidth || 300,
                    height: rect.height || w.customHeight || 200,
                    centerX: rect.left + (rect.width || w.customWidth || 300) / 2,
                    centerY: rect.top + (rect.height || w.customHeight || 200) / 2,
                    isNew: !w.isPositioned,
                    groupId: w.groupId || 'default',
                    preferredRadius: null, // Will be calculated
                    isFixed: isFixed // Mark as fixed so it doesn't move
                };
            });

        if (widgetData.length === 0) return;

        // Group widgets by groupId
        const groups = new Map();
        widgetData.forEach(w => {
            if (!groups.has(w.groupId)) {
                groups.set(w.groupId, []);
            }
            groups.get(w.groupId).push(w);
        });

        // Calculate group centers and ideal positions
        const groupCenters = new Map();
        const groupPositions = new Map(); // Ideal position for each group on screen
        const screenCenterX = winW / 2;
        const screenCenterY = winH / 2;
        const groupArray = Array.from(groups.keys());

        // Position groups in different areas of the screen (radial from center)
        groupArray.forEach((groupId, groupIdx) => {
            const groupWidgets = groups.get(groupId);

            // Calculate current group center - EXCLUDE fixed widgets from center calculation
            // This prevents dragged widgets from pulling their group members
            const movableGroupWidgets = groupWidgets.filter(w => !w.isFixed);
            let sumX = 0, sumY = 0;
            let count = 0;

            if (movableGroupWidgets.length > 0) {
                movableGroupWidgets.forEach(w => {
                    sumX += w.centerX;
                    sumY += w.centerY;
                    count++;
                });
                const currentCenterX = sumX / count;
                const currentCenterY = sumY / count;
                groupCenters.set(groupId, { x: currentCenterX, y: currentCenterY });
            } else {
                // If all widgets in group are fixed, use the first fixed widget's position
                // but don't apply group attraction to it
                if (groupWidgets.length > 0) {
                    const firstWidget = groupWidgets[0];
                    groupCenters.set(groupId, { x: firstWidget.centerX, y: firstWidget.centerY });
                }
            }

            // Calculate ideal position for this group (spread groups around screen)
            const angle = (groupIdx * 2 * Math.PI) / Math.max(1, groupArray.length);
            const groupRadius = Math.min(winW, winH) * 0.25; // Groups positioned at 25% from center
            const idealGroupX = screenCenterX + groupRadius * Math.cos(angle);
            const idealGroupY = screenCenterY + groupRadius * Math.sin(angle);
            groupPositions.set(groupId, { x: idealGroupX, y: idealGroupY });
        });

        // Intelligent force-directed layout algorithm with grouping
        const minSpacing = spacing + 10;
        const iterations = 60; // Number of simulation steps
        const damping = 0.85; // Damping factor to prevent oscillation
        const repulsionStrength = 6000; // How strongly widgets repel each other
        const boundaryStrength = 5000; // How strongly boundaries repel widgets
        const jarvisRepulsionStrength = 10000; // How strongly Jarvis repels widgets
        const groupAttractionStrength = 25; // How strongly widgets are attracted to their group center
        const interGroupRepulsionStrength = 15000; // How strongly different groups repel each other
        const groupPositionAttractionStrength = 8; // How strongly groups are attracted to their ideal position

        // Initialize velocities
        widgetData.forEach(w => {
            w.vx = 0;
            w.vy = 0;
        });

        // Run force-directed simulation
        for (let iter = 0; iter < iterations; iter++) {
            // Update group centers - EXCLUDE fixed widgets from center calculation
            groups.forEach((groupWidgets, groupId) => {
                const movableWidgets = groupWidgets.filter(w => !w.isFixed);
                let sumX = 0, sumY = 0;
                let count = 0;

                if (movableWidgets.length > 0) {
                    movableWidgets.forEach(w => {
                        sumX += w.centerX;
                        sumY += w.centerY;
                        count++;
                    });
                    const centerX = sumX / count;
                    const centerY = sumY / count;
                    groupCenters.set(groupId, { x: centerX, y: centerY });
                } else if (groupWidgets.length > 0) {
                    // If all widgets are fixed, keep center at first fixed widget
                    const firstWidget = groupWidgets[0];
                    groupCenters.set(groupId, { x: firstWidget.centerX, y: firstWidget.centerY });
                }
            });

            widgetData.forEach((w, i) => {
                // Skip fixed widgets - they don't move
                if (w.isFixed) {
                    return;
                }

                let fx = 0, fy = 0; // Force components

                // Attraction to group center (strong within-group cohesion)
                // BUT: Don't apply group attraction if this widget is fixed or if group center is based on fixed widgets
                const groupCenter = groupCenters.get(w.groupId);
                if (groupCenter && !w.isFixed) {
                    // Check if group has any movable widgets (if not, don't apply attraction)
                    const groupWidgets = groups.get(w.groupId) || [];
                    const hasMovableWidgets = groupWidgets.some(gw => !gw.isFixed && gw !== w);

                    // Only apply group attraction if there are other movable widgets in the group
                    // This prevents fixed widgets from pulling others, and prevents widgets from following fixed ones
                    if (hasMovableWidgets) {
                        const dx = groupCenter.x - w.centerX;
                        const dy = groupCenter.y - w.centerY;
                        const distance = Math.sqrt(dx * dx + dy * dy);
                        if (distance > 0) {
                            // Stronger attraction when far from group center
                            const force = groupAttractionStrength * (distance / 100);
                            fx += (dx / distance) * force;
                            fy += (dy / distance) * force;
                        }
                    }
                }

                // Repulsion from widgets in OTHER groups (inter-group separation)
                // Also repulse from fixed widgets
                widgetData.forEach((other, j) => {
                    if (i === j) return;
                    if (w.groupId === other.groupId && !other.isFixed) return; // Same group - handled by group attraction (unless other is fixed)

                    const dx = w.centerX - other.centerX;
                    const dy = w.centerY - other.centerY;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    const minDistance = (w.width + other.width) / 2 + (w.height + other.height) / 2 + minSpacing * 2;

                    // Stronger repulsion from fixed widgets
                    const repulsion = other.isFixed ? interGroupRepulsionStrength * 1.5 : interGroupRepulsionStrength;

                    if (distance < minDistance * 2 && distance > 0) {
                        const force = repulsion / (distance * distance);
                        fx += (dx / distance) * force;
                        fy += (dy / distance) * force;
                    }
                });

                // Repulsion from widgets in SAME group (prevent overlap within group)
                // Fixed widgets in same group still repel, but don't cause group attraction
                widgetData.forEach((other, j) => {
                    if (i === j) return;
                    if (w.groupId !== other.groupId) return; // Different group - already handled

                    const dx = w.centerX - other.centerX;
                    const dy = w.centerY - other.centerY;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    const minDistance = (w.width + other.width) / 2 + (w.height + other.height) / 2 + minSpacing;

                    // Stronger repulsion from fixed widgets to push away from them
                    const repulsion = other.isFixed ? repulsionStrength * 2.0 : repulsionStrength;

                    if (distance < minDistance && distance > 0) {
                        const force = repulsion / (distance * distance);
                        fx += (dx / distance) * force;
                        fy += (dy / distance) * force;
                    }
                });

                // Attraction of group center to ideal position (move entire groups)
                // BUT: Don't apply this if widget is fixed or if group is all fixed widgets
                const idealGroupPos = groupPositions.get(w.groupId);
                if (idealGroupPos && groupCenter && !w.isFixed) {
                    const groupWidgets = groups.get(w.groupId) || [];
                    const hasMovableWidgets = groupWidgets.some(gw => !gw.isFixed);

                    // Only apply group position attraction if there are movable widgets
                    if (hasMovableWidgets) {
                        const dx = idealGroupPos.x - groupCenter.x;
                        const dy = idealGroupPos.y - groupCenter.y;
                        const distance = Math.sqrt(dx * dx + dy * dy);
                        if (distance > 50) {
                            // Apply force to move group toward ideal position
                            const force = groupPositionAttractionStrength * (distance / 200);
                            fx += (dx / distance) * force;
                            fy += (dy / distance) * force;
                        }
                    }
                }

                // Repulsion from Jarvis
                const dxJarvis = w.centerX - jarvisRect.centerX;
                const dyJarvis = w.centerY - jarvisRect.centerY;
                const distJarvis = Math.sqrt(dxJarvis * dxJarvis + dyJarvis * dyJarvis);

                if (distJarvis < jarvisRect.radius && distJarvis > 0) {
                    const force = jarvisRepulsionStrength / (distJarvis * distJarvis);
                    fx += (dxJarvis / distJarvis) * force;
                    fy += (dyJarvis / distJarvis) * force;
                }

                // Boundary repulsion
                const leftDist = w.x - margin;
                const rightDist = (winW - margin) - (w.x + w.width);
                const topDist = w.y - margin;
                const bottomDist = (winH - margin) - (w.y + w.height);

                if (leftDist < 50) fx += boundaryStrength / (leftDist + 1);
                if (rightDist < 50) fx -= boundaryStrength / (rightDist + 1);
                if (topDist < 50) fy += boundaryStrength / (topDist + 1);
                if (bottomDist < 50) fy -= boundaryStrength / (bottomDist + 1);


                // Skip position updates for fixed widgets
                if (w.isFixed) {
                    return;
                }

                // Update velocity with damping
                w.vx = (w.vx + fx) * damping;
                w.vy = (w.vy + fy) * damping;

                // Limit maximum velocity for stability
                const maxVel = 15;
                const vel = Math.sqrt(w.vx * w.vx + w.vy * w.vy);
                if (vel > maxVel) {
                    w.vx = (w.vx / vel) * maxVel;
                    w.vy = (w.vy / vel) * maxVel;
                }

                // Update position
                w.x += w.vx;
                w.y += w.vy;

                // Clamp to boundaries
                w.x = Math.max(margin, Math.min(w.x, winW - w.width - margin));
                w.y = Math.max(margin, Math.min(w.y, winH - w.height - margin));

                // Update center
                w.centerX = w.x + w.width / 2;
                w.centerY = w.y + w.height / 2;
            });
        }

        // Final pass: resolve any remaining overlaps
        // Only move non-fixed widgets away from fixed ones
        for (let i = 0; i < widgetData.length; i++) {
            const w = widgetData[i];

            // Skip fixed widgets - they don't move
            if (w.isFixed) continue;

            for (let j = i + 1; j < widgetData.length; j++) {
                const other = widgetData[j];

                // Check overlap
                const overlapX = Math.min(w.x + w.width, other.x + other.width) - Math.max(w.x, other.x);
                const overlapY = Math.min(w.y + w.height, other.y + other.height) - Math.max(w.y, other.y);

                if (overlapX > 0 && overlapY > 0) {
                    // Separate widgets
                    const dx = w.centerX - other.centerX;
                    const dy = w.centerY - other.centerY;
                    const distance = Math.sqrt(dx * dx + dy * dy);

                    if (distance > 0) {
                        const separation = (overlapX + overlapY) / 2 + minSpacing;
                        const moveX = (dx / distance) * separation * 0.5;
                        const moveY = (dy / distance) * separation * 0.5;

                        // If other is fixed, only move w
                        if (other.isFixed) {
                            w.x += moveX * 2;
                            w.y += moveY * 2;
                        } else {
                            // Move both widgets apart
                            w.x += moveX;
                            w.y += moveY;
                            other.x -= moveX;
                            other.y -= moveY;
                        }

                        // Re-clamp
                        w.x = Math.max(margin, Math.min(w.x, winW - w.width - margin));
                        w.y = Math.max(margin, Math.min(w.y, winH - w.height - margin));
                        if (!other.isFixed) {
                            other.x = Math.max(margin, Math.min(other.x, winW - other.width - margin));
                            other.y = Math.max(margin, Math.min(other.y, winH - other.height - margin));
                        }

                        // Update centers
                        w.centerX = w.x + w.width / 2;
                        w.centerY = w.y + w.height / 2;
                        if (!other.isFixed) {
                            other.centerX = other.x + other.width / 2;
                            other.centerY = other.y + other.height / 2;
                        }
                    }
                }
            }
        }

        // Apply final positions to all widgets (skip fixed widgets - they stay where they are)
        widgetData.forEach(w => {
            // Don't reposition fixed widgets - they maintain their current position
            if (w.isFixed) {
                // Just mark as positioned, but don't move it
                w.widget.isPositioned = true;
                return;
            }
            w.widget.isPositioned = true;
            w.widget.setPosition(Math.round(w.x), Math.round(w.y));
        });

        // Update focus states after layout (skip layout to avoid loop)
        this.updateWidgetFocus(true);
    },

    startDragging(widget) {
        this.isDragging = true;
        this.draggedWidget = widget;
    },

    stopDragging() {
        const wasDragging = this.isDragging;
        const dragged = this.draggedWidget;

        this.isDragging = false;
        this.draggedWidget = null;

        // Mark the dragged widget as fixed PERMANENTLY so it maintains its position
        // It will only be unfixed if the user manually moves it again
        if (dragged) {
            dragged.isPositioned = true;
            this.fixedWidgets.add(dragged);
        }

        // Don't trigger layout - fixed widgets stay fixed permanently
    },

    startResizing(widget) {
        this.isResizing = true;
        this.resizedWidget = widget;
    },

    stopResizing() {
        const wasResizing = this.isResizing;
        const resized = this.resizedWidget;

        this.isResizing = false;
        this.resizedWidget = null;

        // Mark the resized widget as fixed PERMANENTLY so it maintains its position
        // It will only be unfixed if the user manually resizes it again
        if (resized) {
            resized.isPositioned = true;
            this.fixedWidgets.add(resized);
        }

        // Don't trigger layout - fixed widgets stay fixed permanently
    }
};

// Make input active when clicked or focused
if (textInputContainer && textInput) {
    textInputContainer.addEventListener('click', function () {
        textInputContainer.classList.add('active');
        textInput.focus();
    });
}

// Handle submission with Enter key
if (textInput) {
    textInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            // Add a brief lighting effect when sending
            textInputContainer.style.boxShadow = '0 0 25px rgba(0, 149, 255, 0.35), inset 0 0 15px rgba(0, 149, 255, 0.2)';

            sendMessage();

            // Keep the input field expanded
            textInputContainer.classList.add('active');

            // Return to normal lighting after a moment
            setTimeout(() => {
                textInputContainer.style.boxShadow = '';
                // Focus back on the input
                textInput.focus();
            }, 300);
        }
    });

    // Hide when focus is lost and input is empty
    textInput.addEventListener('blur', function () {
        if (textInput.value.trim() === '') {
            textInputContainer.classList.remove('active');
        }
    });
}

// Fixed and complete sendMessage function
function sendMessage() {
    const message = textInput.value.trim();

    if (message) {
        console.log("Sending message: " + message);  // Debug line

        // Display the user message in the output area
        eel.printToOutput("User: " + message);

        // Call the Python function to process the message
        eel.process_text_input(message);

        // Clear the input field
        textInput.value = '';
    }
}

// Make sure the function is exposed to Eel
eel.expose(sendMessage);

// Handle window resize smoothly
let resizeTimeout;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        if (window.WidgetManager && window.WidgetManager.widgets.length > 0) {
            // Only layout on resize if no widgets are fixed
            if (window.WidgetManager.fixedWidgets.size === 0 && !window.WidgetManager.isDragging && !window.WidgetManager.isResizing) {
                window.WidgetManager.layoutWidgets();
            }
        }
    }, 150);
});

// Function to update the output area
eel.expose(updateOutput);
function updateOutput(text) {
    const outputArea = document.getElementById('output-area');
    outputArea.innerHTML += '<div>' + text + '</div>';
    // Auto-scroll to the bottom
    outputArea.scrollTop = outputArea.scrollHeight;
}

// Widget awareness functions - allow AI to query widget information
function getAllWidgets() {
    try {
        console.log('[getAllWidgets] Getting all widgets...');
        console.log('[getAllWidgets] WidgetManager exists:', !!window.WidgetManager);
        console.log('[getAllWidgets] WidgetManager.widgets:', window.WidgetManager ? window.WidgetManager.widgets : 'N/A');
        console.log('[getAllWidgets] WidgetManager.widgets.length:', window.WidgetManager ? window.WidgetManager.widgets.length : 'N/A');

        // Also check DOM directly
        const domWidgets = document.querySelectorAll('.widget');
        console.log(`[getAllWidgets] Found ${domWidgets.length} widgets in DOM`);
        if (domWidgets.length > 0) {
            console.log('[getAllWidgets] DOM widget titles:');
            domWidgets.forEach((w, i) => {
                const titleEl = w.querySelector('.widget-title');
                const title = titleEl ? titleEl.textContent.trim() : 'NO TITLE';
                console.log(`[getAllWidgets]   DOM widget ${i}: "${title}" (type: ${w.getAttribute('data-type')})`);
            });
        }

        const widgets = [];

        // Use WidgetManager first (most reliable)
        if (window.WidgetManager && window.WidgetManager.widgets && window.WidgetManager.widgets.length > 0) {
            console.log(`[getAllWidgets] Found ${window.WidgetManager.widgets.length} widgets in WidgetManager`);
            window.WidgetManager.widgets.forEach((widget, index) => {
                const element = widget.element;
                if (!element) {
                    console.log(`[getAllWidgets] Widget ${index} has no element, skipping`);
                    return;
                }

                const titleEl = element.querySelector('.widget-title');
                const contentEl = element.querySelector('.widget-content');
                const title = titleEl ? titleEl.textContent.trim() : 'NO TITLE';
                const type = element.getAttribute('data-type') || 'unknown';
                const widgetId = element.id || 'NO ID';

                console.log(`[getAllWidgets] Widget ${index}: "${title}" (${type})`);

                const widgetInfo = {
                    id: widgetId,
                    title: title,
                    type: type
                };

                // Add type-specific information
                if (type === 'video') {
                    widgetInfo.videoUrl = element.dataset.videoUrl || null;
                    widgetInfo.videoId = element.dataset.videoId || null;
                    const iframe = element.querySelector('iframe');
                    widgetInfo.iframeSrc = iframe ? iframe.src : null;
                    console.log(`[getAllWidgets] Video widget data:`, {
                        videoUrl: widgetInfo.videoUrl,
                        videoId: widgetInfo.videoId,
                        hasDataset: !!element.dataset,
                        datasetKeys: element.dataset ? Object.keys(element.dataset) : []
                    });
                } else if (type === 'image') {
                    const img = element.querySelector('img');
                    widgetInfo.imageSrc = img ? img.src : null;
                } else if (type === 'text') {
                    widgetInfo.textContent = contentEl ? contentEl.textContent.trim() : null;
                } else if (type === 'notes') {
                    const textarea = contentEl ? contentEl.querySelector('textarea') : null;
                    widgetInfo.textContent = textarea ? textarea.value : null;
                }

                widgets.push(widgetInfo);
            });
        }

        // Fallback: Query DOM directly if WidgetManager is empty
        if (widgets.length === 0) {
            console.log('[getAllWidgets] WidgetManager empty, using DOM query results...');
            // domWidgets already queried above for logging
            domWidgets.forEach((widget, index) => {
                const titleEl = widget.querySelector('.widget-title');
                const contentEl = widget.querySelector('.widget-content');
                const title = titleEl ? titleEl.textContent.trim() : 'NO TITLE';
                const type = widget.getAttribute('data-type') || 'unknown';
                const widgetId = widget.id || 'NO ID';

                console.log(`[getAllWidgets] DOM widget ${index}: "${title}" (${type})`);

                const widgetInfo = {
                    id: widgetId,
                    title: title,
                    type: type
                };

                // Add type-specific information
                if (type === 'video') {
                    widgetInfo.videoUrl = widget.dataset.videoUrl || null;
                    widgetInfo.videoId = widget.dataset.videoId || null;
                    const iframe = widget.querySelector('iframe');
                    widgetInfo.iframeSrc = iframe ? iframe.src : null;
                    console.log(`[getAllWidgets] DOM video widget data:`, {
                        videoUrl: widgetInfo.videoUrl,
                        videoId: widgetInfo.videoId,
                        hasDataset: !!widget.dataset,
                        datasetKeys: widget.dataset ? Object.keys(widget.dataset) : []
                    });
                } else if (type === 'image') {
                    const img = widget.querySelector('img');
                    widgetInfo.imageSrc = img ? img.src : null;
                } else if (type === 'text') {
                    widgetInfo.textContent = contentEl ? contentEl.textContent.trim() : null;
                } else if (type === 'notes') {
                    const textarea = contentEl ? contentEl.querySelector('textarea') : null;
                    widgetInfo.textContent = textarea ? textarea.value : null;
                }

                widgets.push(widgetInfo);
            });
        }

        console.log(`[getAllWidgets] Returning ${widgets.length} widgets`);
        return widgets;
    } catch (error) {
        console.error('[getAllWidgets] Error getting all widgets:', error);
        console.error('[getAllWidgets] Stack trace:', error.stack);
        return [];
    }
}

function getWidgetByTitle(title) {
    try {
        console.log(`[getWidgetByTitle] Searching for widget with title: "${title}"`);
        console.log(`[getWidgetByTitle] WidgetManager exists: ${!!window.WidgetManager}`);
        console.log(`[getWidgetByTitle] WidgetManager.widgets:`, window.WidgetManager ? window.WidgetManager.widgets : 'N/A');

        const searchTitle = title.trim().toUpperCase();
        console.log(`[getWidgetByTitle] Normalized search title: "${searchTitle}"`);

        // Also check DOM directly first for logging
        const domWidgets = document.querySelectorAll('.widget');
        console.log(`[getWidgetByTitle] Found ${domWidgets.length} widgets in DOM`);
        if (domWidgets.length > 0) {
            console.log('[getWidgetByTitle] DOM widget titles:');
            domWidgets.forEach((w, i) => {
                const titleEl = w.querySelector('.widget-title');
                const title = titleEl ? titleEl.textContent.trim() : 'NO TITLE';
                console.log(`[getWidgetByTitle]   DOM widget ${i}: "${title}" -> "${title.toUpperCase()}"`);
            });
        }

        // Try WidgetManager first
        let foundWidget = null;
        if (window.WidgetManager && window.WidgetManager.widgets) {
            console.log(`[getWidgetByTitle] Checking ${window.WidgetManager.widgets.length} widgets in WidgetManager`);
            for (const widget of window.WidgetManager.widgets) {
                const element = widget.element;
                if (!element) continue;

                const titleEl = element.querySelector('.widget-title');
                if (!titleEl) continue;

                const widgetTitle = titleEl.textContent.trim().toUpperCase();
                console.log(`[getWidgetByTitle] Comparing "${widgetTitle}" with "${searchTitle}"`);

                // Exact match or number match for videos (e.g., "VIDEO 1" matches "VIDEO 1")
                const exactMatch = widgetTitle === searchTitle;
                let numberMatch = false;

                if (widgetTitle.includes('VIDEO') && searchTitle.includes('VIDEO')) {
                    const widgetNumber = widgetTitle.match(/\d+/);
                    const searchNumber = searchTitle.match(/\d+/);
                    if (widgetNumber && searchNumber && widgetNumber[0] === searchNumber[0]) {
                        numberMatch = true;
                        console.log(`[getWidgetByTitle] Number match found: ${widgetNumber[0]}`);
                    }
                }

                if (exactMatch || numberMatch) {
                    foundWidget = element;
                    console.log(`[getWidgetByTitle] Found widget! Title: "${widgetTitle}"`);
                    break;
                }
            }
        }

        // Fallback: Query DOM directly
        if (!foundWidget) {
            console.log(`[getWidgetByTitle] WidgetManager search failed, querying DOM directly...`);
            const widgets = document.querySelectorAll('.widget');
            console.log(`[getWidgetByTitle] Found ${widgets.length} widgets in DOM`);
            for (const widget of widgets) {
                const titleEl = widget.querySelector('.widget-title');
                if (!titleEl) continue;

                const widgetTitle = titleEl.textContent.trim().toUpperCase();
                console.log(`[getWidgetByTitle] DOM widget title: "${widgetTitle}"`);

                // Exact match or number match for videos
                const exactMatch = widgetTitle === searchTitle;
                let numberMatch = false;

                if (widgetTitle.includes('VIDEO') && searchTitle.includes('VIDEO')) {
                    const widgetNumber = widgetTitle.match(/\d+/);
                    const searchNumber = searchTitle.match(/\d+/);
                    if (widgetNumber && searchNumber && widgetNumber[0] === searchNumber[0]) {
                        numberMatch = true;
                        console.log(`[getWidgetByTitle] DOM number match found: ${widgetNumber[0]}`);
                    }
                }

                if (exactMatch || numberMatch) {
                    foundWidget = widget;
                    console.log(`[getWidgetByTitle] Found widget in DOM! Title: "${widgetTitle}"`);
                    break;
                }
            }
        }

        if (!foundWidget) {
            console.log(`[getWidgetByTitle] No widget found with title "${title}"`);
            // Return a helpful debug message
            const allWidgets = getAllWidgets();
            console.log(`[getWidgetByTitle] Available widgets:`, allWidgets.map(w => w.title));
            return null;
        }

        const contentEl = foundWidget.querySelector('.widget-content');
        const type = foundWidget.getAttribute('data-type') || 'unknown';
        const widgetId = foundWidget.id || 'NO ID';
        const titleEl = foundWidget.querySelector('.widget-title');

        const widgetInfo = {
            id: widgetId,
            title: titleEl ? titleEl.textContent.trim() : 'NO TITLE',
            type: type
        };

        // Add type-specific information
        if (type === 'video') {
            widgetInfo.videoUrl = foundWidget.dataset.videoUrl || null;
            widgetInfo.videoId = foundWidget.dataset.videoId || null;
            const iframe = foundWidget.querySelector('iframe');
            widgetInfo.iframeSrc = iframe ? iframe.src : null;
            console.log(`[getWidgetByTitle] Video widget info:`, {
                videoUrl: widgetInfo.videoUrl,
                videoId: widgetInfo.videoId,
                iframeSrc: widgetInfo.iframeSrc
            });
        } else if (type === 'image') {
            const img = foundWidget.querySelector('img');
            widgetInfo.imageSrc = img ? img.src : null;
        } else if (type === 'text') {
            widgetInfo.textContent = contentEl ? contentEl.textContent.trim() : null;
        } else if (type === 'notes') {
            const textarea = contentEl ? contentEl.querySelector('textarea') : null;
            widgetInfo.textContent = textarea ? textarea.value : null;
        }

        console.log(`[getWidgetByTitle] Returning widget info:`, widgetInfo);
        return widgetInfo;
    } catch (error) {
        console.error('[getWidgetByTitle] Error getting widget by title:', error);
        console.error('[getWidgetByTitle] Stack trace:', error.stack);
        return null;
    }
}

// Function to update transcript indicator
function updateTranscriptIndicator(title, status) {
    try {
        // Find the widget by title
        const widgets = document.querySelectorAll('.widget');
        for (const widget of widgets) {
            const titleEl = widget.querySelector('.widget-title');
            if (titleEl && titleEl.textContent.trim() === title) {
                const indicator = widget.querySelector('.transcript-indicator');
                if (indicator) {
                    if (status === 'loading') {
                        // Show loading icon with X icon on hover - clickable to cancel
                        indicator.innerHTML = `
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="loading-spinner">
                                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="rgba(33, 150, 243, 0.2)" opacity="0.3"/>
                                <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" opacity="0.9"/>
                            </svg>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="cancel-x-icon" style="display: none; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); pointer-events: all; cursor: pointer;">
                                <path d="M8 8l8 8M16 8l-8 8" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                        `;
                        indicator.title = 'Generating summary... (hover to cancel)';
                        indicator.style.color = '#2196F3';
                        indicator.style.opacity = '1';
                        indicator.style.cursor = 'pointer';
                        // Keep position absolute (don't override CSS)

                        // Remove any existing click handlers by cloning and replacing
                        const oldIndicator = indicator;
                        const newIndicator = oldIndicator.cloneNode(true);
                        const parent = oldIndicator.parentNode;
                        parent.replaceChild(newIndicator, oldIndicator);

                        // Get the new indicator element (the one we just inserted)
                        const clickableIndicator = parent.querySelector('.transcript-indicator');

                        // Add hover and click handlers
                        if (clickableIndicator) {
                            const loadingSpinner = clickableIndicator.querySelector('.loading-spinner');
                            const cancelXIcon = clickableIndicator.querySelector('.cancel-x-icon');

                            // Show X icon on hover, fade spinner
                            clickableIndicator.addEventListener('mouseenter', () => {
                                if (loadingSpinner && cancelXIcon) {
                                    loadingSpinner.style.opacity = '0.3';
                                    cancelXIcon.style.display = 'block';
                                }
                            });

                            // Hide X icon when not hovering, show spinner
                            clickableIndicator.addEventListener('mouseleave', () => {
                                if (loadingSpinner && cancelXIcon) {
                                    loadingSpinner.style.opacity = '1';
                                    cancelXIcon.style.display = 'none';
                                }
                            });

                            // Add click handler to cancel summarization (only when X is visible)
                            if (cancelXIcon) {
                                cancelXIcon.addEventListener('click', (e) => {
                                    e.stopPropagation();
                                    e.preventDefault();

                                    console.log(`[Cancel] Requesting cancellation for: ${title}`);

                                    // Immediately remove the indicator (instant, no animation)
                                    if (clickableIndicator && clickableIndicator.parentElement) {
                                        clickableIndicator.remove();
                                    }

                                    // Call the backend to actually cancel
                                    if (typeof eel !== 'undefined' && eel.cancel_summarization) {
                                        eel.cancel_summarization(title)().then(result => {
                                            console.log('[Cancel]', result);
                                        }).catch(err => {
                                            console.error('[Cancel] Error:', err);
                                        });
                                    }
                                });
                            }
                        }
                    } else if (status === 'cancelled') {
                        // Show cancelled icon
                        indicator.innerHTML = `
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="rgba(158, 158, 158, 0.2)"/>
                                <path d="M8 8l8 8M16 8l-8 8" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
                            </svg>
                        `;
                        indicator.title = 'Summarization cancelled';
                        indicator.style.color = '#9E9E9E';
                        indicator.style.opacity = '0.7';
                        indicator.style.cursor = 'default';

                        // Hide the indicator after 3 seconds
                        setTimeout(() => {
                            if (indicator && indicator.parentElement) {
                                indicator.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                                indicator.style.opacity = '0';
                                indicator.style.transform = 'translateY(-50%) scale(0.8)';
                                setTimeout(() => {
                                    if (indicator && indicator.parentElement) {
                                        indicator.remove();
                                    }
                                }, 500); // Wait for fade-out animation
                            }
                        }, 3000); // 3 seconds
                    } else if (status === 'complete') {
                        // Show check icon
                        indicator.innerHTML = `
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="rgba(76, 175, 80, 0.2)"/>
                                <path d="M8 12l2 2 4-4" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                        `;
                        indicator.title = 'Summary generated';
                        indicator.style.color = '#4CAF50';
                        indicator.style.opacity = '1';

                        // Hide the indicator after 10 seconds
                        setTimeout(() => {
                            if (indicator && indicator.parentElement) {
                                indicator.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                                indicator.style.opacity = '0';
                                indicator.style.transform = 'translateY(-50%) scale(0.8)';
                                setTimeout(() => {
                                    if (indicator && indicator.parentElement) {
                                        indicator.remove();
                                    }
                                }, 500); // Wait for fade-out animation
                            }
                        }, 10000); // 10 seconds
                    }
                    break;
                }
            }
        }
    } catch (error) {
        console.error('[updateTranscriptIndicator] Error:', error);
    }
}

// Expose widget awareness functions to Python
// Enhanced function to get all widgets with full state for workspace saving
function getAllWidgetsForWorkspace() {
    try {
        const widgets = [];
        
        if (window.WidgetManager && window.WidgetManager.widgets) {
            window.WidgetManager.widgets.forEach((widget) => {
                const element = widget.element;
                if (!element) return;
                
                const rect = element.getBoundingClientRect();
                const titleEl = element.querySelector('.widget-title');
                const contentEl = element.querySelector('.widget-content');
                const title = titleEl ? titleEl.textContent.trim() : 'NO TITLE';
                const type = element.getAttribute('data-type') || 'unknown';
                const widgetId = element.id || 'NO ID';
                
                const widgetData = {
                    id: widgetId,
                    title: title,
                    type: type,
                    x: Math.round(rect.left),
                    y: Math.round(rect.top),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    customWidth: widget.customWidth || null,
                    customHeight: widget.customHeight || null,
                    groupId: widget.groupId || null,
                    zIndex: parseInt(element.style.zIndex) || 1000
                };
                
                // Add type-specific content
                if (type === 'video') {
                    widgetData.videoUrl = element.dataset.videoUrl || null;
                    widgetData.videoId = element.dataset.videoId || null;
                } else if (type === 'image') {
                    const img = element.querySelector('img');
                    widgetData.imageSrc = img ? img.src : null;
                } else if (type === 'text') {
                    widgetData.textContent = contentEl ? contentEl.textContent.trim() : null;
                } else if (type === 'notes') {
                    const textarea = contentEl ? contentEl.querySelector('textarea') : null;
                    let notesContent = textarea ? textarea.value : null;
                    
                    // Handle data URLs in notes - validate and truncate if too long
                    if (notesContent) {
                        // Check for data URLs (base64 images)
                        const dataUrlPattern = /data:image\/[^;]+;base64,[A-Za-z0-9+/=]+/g;
                        const matches = notesContent.match(dataUrlPattern);
                        
                        if (matches) {
                            // Replace very long data URLs with a placeholder to prevent workspace corruption
                            matches.forEach(dataUrl => {
                                // If data URL is longer than 1MB (approximately 1,300,000 characters), truncate it
                                if (dataUrl.length > 1300000) {
                                    console.warn('[Workspace] Truncating very long data URL in notes to prevent workspace corruption');
                                    notesContent = notesContent.replace(dataUrl, '[Image data too large - removed to preserve workspace]');
                                }
                            });
                        }
                    }
                    
                    widgetData.textContent = notesContent;
                } else if (type === 'weather') {
                    widgetData.weatherData = contentEl ? contentEl.textContent.trim() : null;
                } else if (type === 'time') {
                    widgetData.timeData = contentEl ? contentEl.textContent.trim() : null;
                    // Check if military time format
                    const timeText = widgetData.timeData || '';
                    widgetData.militaryTime = !timeText.includes('AM') && !timeText.includes('PM');
                } else if (type === 'timer') {
                    widgetData.timerData = contentEl ? contentEl.textContent.trim() : null;
                } else if (type === 'calculator') {
                    const iframe = element.querySelector('iframe');
                    widgetData.calculatorUrl = iframe ? iframe.src : null;
                } else if (type === 'gesture_control') {
                    // Gesture control widget - no special data to save
                    widgetData.gestureControlData = null;
                } else if (type === 'alarm') {
                    widgetData.alarmLabel = contentEl ? contentEl.textContent.trim() : null;
                } else if (type === 'reminder') {
                    widgetData.reminderLabel = contentEl ? contentEl.textContent.trim() : null;
                }
                
                widgets.push(widgetData);
            });
        }
        
        return widgets;
    } catch (error) {
        console.error('[getAllWidgetsForWorkspace] Error:', error);
        return [];
    }
}

// Function to restore widgets from workspace data
function restoreWorkspace(workspaceData) {
    try {
        console.log('[restoreWorkspace] Starting restoration, widgets:', workspaceData.widgets?.length || 0);
        
        // Clear all existing widgets first
        if (window.WidgetManager) {
            const widgetsToClose = window.WidgetManager.widgets.slice();
            widgetsToClose.forEach(w => {
                try {
                    w.close();
                } catch (e) {
                    console.error('[restoreWorkspace] Error closing widget:', e);
                }
            });
        }
        
        // Small delay to ensure widgets are cleared
        setTimeout(() => {
            const widgets = workspaceData.widgets || [];
            console.log('[restoreWorkspace] Restoring', widgets.length, 'widgets');
            
            widgets.forEach((widgetData, index) => {
                // Add small delay between widget creation to prevent layout issues
                setTimeout(() => {
                    restoreWidget(widgetData);
                }, index * 100); // 100ms delay between each widget
            });
        }, 200);
        
        return { success: true, message: `Restored ${(workspaceData.widgets || []).length} widgets` };
    } catch (error) {
        console.error('[restoreWorkspace] Error:', error);
        return { success: false, message: `Error restoring workspace: ${error.message}` };
    }
}

function restoreWidget(widgetData) {
    try {
        const { type, title, x, y, customWidth, customHeight, groupId } = widgetData;
        console.log('[restoreWidget] Restoring widget:', type, title);
        
        // Store the widget data for positioning after creation
        const positionData = { x, y, width: widgetData.width, height: widgetData.height, id: widgetData.id };
        
        if (type === 'video' && widgetData.videoUrl) {
            // Skip auto-summarization when restoring from workspace
            eel.create_video_widget(widgetData.videoUrl, title, true);
        } else if (type === 'image' && widgetData.imageSrc) {
            eel.create_image_widget(widgetData.imageSrc, title, customWidth, customHeight, groupId);
        } else if (type === 'text' && widgetData.textContent) {
            eel.create_text_widget(widgetData.textContent, title, groupId);
        } else if (type === 'notes') {
            let notesText = widgetData.textContent || '';
            
            // Validate and clean data URLs before restoring
            if (notesText) {
                try {
                    // Check for data URLs and validate them
                    const dataUrlPattern = /data:image\/[^;]+;base64,[A-Za-z0-9+/=]+/g;
                    const matches = notesText.match(dataUrlPattern);
                    
                    if (matches) {
                        // Validate each data URL
                        matches.forEach(dataUrl => {
                            try {
                                // Check if data URL is valid and not too long
                                if (dataUrl.length > 2000000) { // 2MB limit
                                    console.warn('[Workspace] Removing invalid/too large data URL from notes');
                                    notesText = notesText.replace(dataUrl, '[Image data invalid or too large]');
                                } else {
                                    // Try to validate the base64 data
                                    const base64Data = dataUrl.split(',')[1];
                                    if (!base64Data || base64Data.length === 0) {
                                        throw new Error('Invalid base64 data');
                                    }
                                }
                            } catch (e) {
                                console.warn('[Workspace] Error validating data URL, replacing with placeholder:', e);
                                notesText = notesText.replace(dataUrl, '[Image data error - removed]');
                            }
                        });
                    }
                } catch (e) {
                    console.error('[Workspace] Error processing notes content:', e);
                    // If there's an error, try to remove all data URLs as a fallback
                    notesText = notesText.replace(/data:image\/[^;]+;base64,[A-Za-z0-9+/=]+/g, '[Image data error - removed]');
                }
            }
            
            eel.create_notes_widget(title, notesText, groupId);
        } else if (type === 'weather' && widgetData.weatherData) {
            try {
                const weatherData = typeof widgetData.weatherData === 'string' ? JSON.parse(widgetData.weatherData) : widgetData.weatherData;
                eel.create_weather_widget(JSON.stringify(weatherData), title, groupId);
            } catch (e) {
                eel.create_weather_widget(widgetData.weatherData, title, groupId);
            }
        } else if (type === 'time') {
            eel.create_time_widget(groupId, widgetData.militaryTime || false);
        } else if (type === 'calculator') {
            eel.create_calculator_widget(groupId);
        } else if (type === 'gesture_control') {
            eel.create_gesture_control_widget(groupId);
        } else if (type === 'timer' && widgetData.timerData) {
            // Extract duration from timer data if available
            try {
                const timerData = typeof widgetData.timerData === 'string' ? JSON.parse(widgetData.timerData) : widgetData.timerData;
                const duration = timerData.duration_seconds || 60;
                eel.create_timer_widget(duration, groupId);
            } catch (e) {
                eel.create_timer_widget(60, groupId);
            }
        } else if (type === 'alarm' && widgetData.alarmLabel) {
            eel.create_alarm_widget(widgetData.alarmLabel, groupId);
        } else if (type === 'reminder' && widgetData.reminderLabel) {
            eel.create_reminder_widget(widgetData.reminderLabel, groupId);
        }
        
        // After widget is created, set its position
        // We need to wait for the widget to be created, then position it
        // Try multiple times with increasing delays to find the widget
        let attempts = 0;
        const maxAttempts = 20;
        const checkInterval = setInterval(() => {
            attempts++;
            let widgetElement = null;
            
            // Try to find by ID first
            if (positionData.id) {
                widgetElement = document.getElementById(positionData.id);
            }
            
            // If not found by ID, try to find by title (widgets get new IDs when created)
            if (!widgetElement && title) {
                const allWidgets = document.querySelectorAll('.widget');
                for (const w of allWidgets) {
                    const titleEl = w.querySelector('.widget-title');
                    if (titleEl && titleEl.textContent.trim() === title) {
                        widgetElement = w;
                        break;
                    }
                }
            }
            
            if (widgetElement && positionData.x !== undefined && positionData.y !== undefined) {
                clearInterval(checkInterval);
                
                widgetElement.style.left = `${positionData.x}px`;
                widgetElement.style.top = `${positionData.y}px`;
                if (positionData.width) {
                    widgetElement.style.width = `${positionData.width}px`;
                }
                if (positionData.height) {
                    widgetElement.style.height = `${positionData.height}px`;
                }
                
                // Find the widget in WidgetManager and update its position
                if (window.WidgetManager) {
                    const widget = window.WidgetManager.widgets.find(w => w.element === widgetElement);
                    if (widget) {
                        widget.setPosition(positionData.x, positionData.y);
                        widget.isPositioned = true;
                        // Mark as fixed so it doesn't get auto-layouted
                        window.WidgetManager.fixedWidgets.add(widget);
                        console.log('[restoreWidget] Positioned widget:', title, 'at', positionData.x, positionData.y);
                    }
                }
            } else if (attempts >= maxAttempts) {
                clearInterval(checkInterval);
                console.warn('[restoreWidget] Could not find widget after', maxAttempts, 'attempts:', title);
            }
        }, 100); // Check every 100ms
    } catch (error) {
        console.error('[restoreWidget] Error restoring widget:', error);
    }
}

eel.expose(getAllWidgets);
eel.expose(getWidgetByTitle);
eel.expose(getAllWidgetsForWorkspace);
eel.expose(restoreWorkspace);

// Make restoreWorkspace available globally
window.restoreWorkspace = restoreWorkspace;
eel.expose(updateTranscriptIndicator);

// Make available globally
window.getAllWidgets = getAllWidgets;
window.getWidgetByTitle = getWidgetByTitle;

// Drag and Drop support for YouTube videos
// Initialize immediately to catch events before Chrome handles them
(function () {
    'use strict';

    let dragCounter = 0;
    let isDraggingOver = false;

    // Helper function to extract URL from drag data
    function extractUrlFromDrag(dataTransfer) {
        // Try multiple data types that Chrome might use
        const types = dataTransfer.types || [];

        // Check for URL in various formats
        let url = null;

        // Try text/uri-list first (standard format)
        if (types.includes('text/uri-list')) {
            url = dataTransfer.getData('text/uri-list');
        }

        // Try text/plain (sometimes Chrome uses this)
        if (!url && types.includes('text/plain')) {
            const text = dataTransfer.getData('text/plain');
            // Check if it looks like a URL
            if (text && (text.startsWith('http://') || text.startsWith('https://'))) {
                url = text;
            }
        }

        // Try URL format (some browsers use this)
        if (!url && types.includes('URL')) {
            url = dataTransfer.getData('URL');
        }

        // Try text/html (Chrome might wrap the link in HTML)
        if (!url && types.includes('text/html')) {
            const html = dataTransfer.getData('text/html');
            if (html) {
                // Try to extract URL from HTML anchor tag
                const match = html.match(/<a[^>]+href=["']([^"']+)["']/i);
                if (match && match[1]) {
                    url = match[1];
                }
            }
        }

        return url;
    }

    // Handle drop event - most critical one
    function handleDrop(e) {
        console.log('=== DROP EVENT FIRED IN SCRIPT.JS ===');

        // PREVENT DEFAULT FIRST - This is critical!
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        e.cancelBubble = true;
        e.returnValue = false;

        // Make sure default is prevented
        if (e.defaultPrevented) {
            console.log('✓ Default prevented successfully');
        } else {
            console.error('✗ WARNING: Default NOT prevented!');
        }

        dragCounter = 0;
        isDraggingOver = false;
        document.body.classList.remove('drag-active');

        // IMPORTANT: dataTransfer is only available synchronously during the drop event
        // Extract data immediately, don't use setTimeout

        if (!e.dataTransfer) {
            console.error('✗ No dataTransfer object!');
            return false;
        }

        const dt = e.dataTransfer;
        const types = Array.from(dt.types || []);
        console.log('DataTransfer types:', types);
        console.log('Files count:', dt.files ? dt.files.length : 0);

        // Check for dropped image files first
        if (dt.files && dt.files.length > 0) {
            const imageFiles = Array.from(dt.files).filter(file => file.type.startsWith('image/'));
            
            if (imageFiles.length > 0) {
                console.log(`✓ Found ${imageFiles.length} image file(s) to process`);
                
                const dropX = e.clientX;
                const dropY = e.clientY;
                
                // Process each image file
                imageFiles.forEach((file, index) => {
                    const reader = new FileReader();
                    
                    reader.onload = function(event) {
                        const dataUrl = event.target.result;
                        const widgetId = `image_${Date.now()}_${index}`;
                        const title = 'IMAGE';
                        const groupId = `group_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                        
                        console.log(`Creating image widget for file: ${file.name}`);
                        
                        // Use window.createWidget to create the image widget
                        if (typeof window.createWidget === 'function') {
                            try {
                                // Position images with slight offset if multiple
                                const offsetX = dropX + (index * 20);
                                const offsetY = dropY + (index * 20);
                                window.createWidget(widgetId, title, 'image', dataUrl, offsetX, offsetY, null, null, groupId);
                                console.log(`✓✓✓ Image widget created successfully: ${title} ✓✓✓`);
                            } catch (err) {
                                console.error('✗✗✗ Error creating image widget:', err);
                            }
                        } else {
                            console.error('✗ createWidget function not available on window');
                        }
                    };
                    
                    reader.onerror = function(error) {
                        console.error('Error reading image file:', error);
                    };
                    
                    // Read the file as data URL
                    reader.readAsDataURL(file);
                });
                
                // Return early since we handled the files
                return false;
            }
        }

        // Extract URL from drag data immediately - try ALL possible formats
        let url = null;

        // Try every possible data format
        const dataFormats = ['text/uri-list', 'URL', 'text/plain', 'text/html', 'text/x-moz-url'];

        for (const format of dataFormats) {
            if (url) break;
            try {
                const data = dt.getData(format);
                if (data) {
                    console.log(`Got data from ${format}:`, data.substring(0, 100));

                    // Check if it's a URL
                    if (data.startsWith('http://') || data.startsWith('https://')) {
                        url = data.trim();
                        console.log(`✓ Found URL in ${format}:`, url);
                        break;
                    }

                    // Check if it's HTML with a link
                    if (format === 'text/html') {
                        const match = data.match(/<a[^>]+href=["']([^"']+)["']/i);
                        if (match && match[1]) {
                            url = match[1];
                            console.log(`✓ Extracted URL from HTML:`, url);
                            break;
                        }
                    }
                }
            } catch (err) {
                // Some formats might not be available, that's OK
                console.log(`Format ${format} not available`);
            }
        }

        // If still no URL, try getting all data without type checking
        if (!url) {
            console.log('Trying to get data without type checking...');
            try {
                // Try all formats in order of preference
                const allFormats = ['text/uri-list', 'URL', 'text/plain', 'text/html'];
                for (const format of allFormats) {
                    try {
                        const data = dt.getData(format);
                        if (data && data.trim()) {
                            // Check if it contains a URL
                            const urlMatch = data.match(/https?:\/\/[^\s<>"']+/i);
                            if (urlMatch) {
                                url = urlMatch[0];
                                console.log(`✓ Found URL pattern in ${format}:`, url);
                                break;
                            }
                        }
                    } catch (e) {
                        // Continue
                    }
                }
            } catch (err) {
                console.error('Error in fallback data extraction:', err);
            }
        }

        console.log('=== FINAL URL:', url, '===');

        if (url) {
            // Clean up URL (remove any trailing characters)
            url = url.trim().split(/[\s<>"']/)[0];

            // Check if it's a YouTube URL
            if (typeof window.getYouTubeVideoId === 'function') {
                const videoId = window.getYouTubeVideoId(url);
                console.log('YouTube Video ID extracted:', videoId);

                if (videoId) {
                    // Create a video widget with numbered title
                    const widgetId = `video_${Date.now()}`;
                    const videoNumber = window.getNextVideoNumber ? window.getNextVideoNumber() : 1;
                    const title = `VIDEO ${videoNumber}`;
                    const groupId = `group_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                    const dropX = e.clientX;
                    const dropY = e.clientY;

                    console.log('Attempting to create widget...', {
                        widgetId, title, url, dropX, dropY,
                        createWidgetAvailable: typeof window.createWidget === 'function'
                    });

                    // Use window.createWidget to ensure we get the global function
                    if (typeof window.createWidget === 'function') {
                        try {
                            window.createWidget(widgetId, title, 'video', url, dropX, dropY, null, null, groupId);
                            console.log('✓✓✓ Widget creation called successfully! ✓✓✓');

                            // Automatically queue the video for summarization after widget creation
                            // Add a small delay to ensure widget is fully created
                            setTimeout(() => {
                                console.log(`[Auto-summarize] Queuing automatic summarization for ${title}`);

                                // Update indicator to loading when summarization starts
                                const widgetElement = document.querySelector(`[data-video-id="${videoId}"]`) ||
                                    Array.from(document.querySelectorAll('.widget')).find(w => {
                                        const titleEl = w.querySelector('.widget-title');
                                        return titleEl && titleEl.textContent.trim() === title;
                                    });

                                if (widgetElement) {
                                    const indicator = widgetElement.querySelector('.transcript-indicator');
                                    if (indicator && widgetElement.dataset.transcriptAvailable === 'true') {
                                        // Show loading icon (spinning)
                                        indicator.innerHTML = `
                                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="loading-spinner">
                                                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="rgba(33, 150, 243, 0.2)" opacity="0.3"/>
                                                <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity="0.8">
                                                    <animateTransform attributeName="transform" type="rotate" dur="1s" repeatCount="indefinite" values="0 12 12;360 12 12"/>
                                                </path>
                                            </svg>
                                        `;
                                        indicator.title = 'Generating summary...';
                                        indicator.style.color = '#2196F3';

                                        // Add CSS animation for spinner
                                        if (!document.getElementById('spinner-style')) {
                                            const style = document.createElement('style');
                                            style.id = 'spinner-style';
                                            style.textContent = `
                                                .transcript-indicator .loading-spinner {
                                                    animation: spin 1s linear infinite;
                                                }
                                                @keyframes spin {
                                                    from { transform: rotate(0deg); }
                                                    to { transform: rotate(360deg); }
                                                }
                                            `;
                                            document.head.appendChild(style);
                                        }
                                    }
                                }

                                if (typeof eel !== 'undefined' && eel.summarize_video_widget_from_title) {
                                    eel.summarize_video_widget_from_title(title)().then(result => {
                                        console.log(`[Auto-summarize] Queued:`, result);

                                        // Note: The actual completion will be handled by the queue worker
                                        // We'll need to expose a function to update the indicator when summary completes
                                    }).catch(err => {
                                        console.error(`[Auto-summarize] Error queueing video:`, err);
                                    });
                                } else {
                                    console.warn('[Auto-summarize] eel.summarize_video_widget_from_title not available');
                                }
                            }, 1000); // 1 second delay to ensure widget is fully initialized
                        } catch (err) {
                            console.error('✗✗✗ Error creating widget:', err);
                        }
                    } else {
                        console.error('✗ createWidget function not available on window');
                        console.log('Window object keys:', Object.keys(window).filter(k => k.includes('create')));
                    }
                } else {
                    console.log('✗ Not a YouTube URL or could not extract video ID from:', url);
                }
            } else {
                console.error('✗ getYouTubeVideoId function not available on window');
            }
        } else {
            console.log('✗✗✗ No URL extracted from drop data ✗✗✗');
            console.log('Debug info:', {
                types: types,
                files: dt.files ? dt.files.length : 0,
                items: dt.items ? dt.items.length : 0
            });
        }

        return false;
    }

    // Handle dragover - critical to prevent default navigation
    function handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        e.cancelBubble = true;

        // Set drop effect to copy to show we're accepting the drop
        if (e.dataTransfer) {
            e.dataTransfer.dropEffect = 'copy';
            // Prevent Chrome from navigating
            e.dataTransfer.effectAllowed = 'copy';
        }

        return false;
    }

    // Handle dragenter
    function handleDragEnter(e) {
        e.preventDefault();
        e.stopPropagation();
        dragCounter++;
        if (!isDraggingOver) {
            isDraggingOver = true;
            document.body.classList.add('drag-active');
        }
        return false;
    }

    // Handle dragleave
    function handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        dragCounter--;
        if (dragCounter <= 0) {
            dragCounter = 0;
            isDraggingOver = false;
            document.body.classList.remove('drag-active');
        }
        return false;
    }

    // Register handlers on multiple levels for maximum coverage
    // CRITICAL: Use capture phase and passive: false to run BEFORE Chrome's handlers
    // and be able to preventDefault

    // Add to documentElement (html) first - highest level
    if (document.documentElement) {
        document.documentElement.addEventListener('dragenter', handleDragEnter, { capture: true, passive: false });
        document.documentElement.addEventListener('dragover', handleDragOver, { capture: true, passive: false });
        document.documentElement.addEventListener('dragleave', handleDragLeave, { capture: true, passive: false });
        document.documentElement.addEventListener('drop', handleDrop, { capture: true, passive: false });
        console.log('Handlers registered on documentElement');
    }

    // Add to document (capture phase)
    document.addEventListener('dragenter', handleDragEnter, { capture: true, passive: false });
    document.addEventListener('dragover', handleDragOver, { capture: true, passive: false });
    document.addEventListener('dragleave', handleDragLeave, { capture: true, passive: false });
    document.addEventListener('drop', handleDrop, { capture: true, passive: false });
    console.log('Handlers registered on document');

    // Also add to window
    window.addEventListener('dragenter', handleDragEnter, { capture: true, passive: false });
    window.addEventListener('dragover', handleDragOver, { capture: true, passive: false });
    window.addEventListener('dragleave', handleDragLeave, { capture: true, passive: false });
    window.addEventListener('drop', handleDrop, { capture: true, passive: false });
    console.log('Handlers registered on window');

    // Also add to body when available
    function addBodyHandlers() {
        if (document.body) {
            document.body.addEventListener('dragenter', handleDragEnter, { capture: true, passive: false });
            document.body.addEventListener('dragover', handleDragOver, { capture: true, passive: false });
            document.body.addEventListener('dragleave', handleDragLeave, { capture: true, passive: false });
            document.body.addEventListener('drop', handleDrop, { capture: true, passive: false });
            console.log('Handlers registered on body');
        }
    }

    if (document.body) {
        addBodyHandlers();
    } else {
        // If body not ready, wait for it
        document.addEventListener('DOMContentLoaded', addBodyHandlers);
    }

    console.log('✓✓✓ Drag and drop handlers fully initialized ✓✓✓');
})();