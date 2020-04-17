(function ($) {

    'use strict';

    var word_count_interval;

    const observer_options = {
        childList: true
    };

    const observer = new MutationObserver(function (mutations) {
        mutations.forEach((mutation) => {
            const mutation_selector = '#' + mutation.target.id;
            const word_count = parseInt(mutation.target.innerText.match(/\d+/)[0], 10);
            const word_count_node = document.querySelector(mutation_selector);
            const word_limit = parseInt($(mutation_selector).parents().eq(5).attr('data-word-limit'), 10);
            const percent_to_get = 20;
            const word_limit_to_show_warning = word_limit - (percent_to_get / 100) * word_limit;

            if (word_count <= word_limit_to_show_warning) {
                word_count_node.setAttribute('data-after-word-count', ' out of ' + word_limit);
                word_count_node.classList.remove('word-count-warning');
                word_count_node.classList.remove('word-count-warning-2');
            }
            else if (word_count > word_limit_to_show_warning && word_count <= word_limit) {
                word_count_node.setAttribute('data-after-word-count', ' out of ' + word_limit + ' (Close to the limit)');
                word_count_node.classList.remove('word-count-warning-2');
                word_count_node.classList.add('word-count-warning');
            }
            else if (word_count > word_limit) {
                word_count_node.setAttribute('data-after-word-count', ' out of ' + word_limit + ' (Over the limit)');
                word_count_node.classList.add('word-count-warning-2');
            }
        });
    });

    function word_count_alert() {
        const word_counts = document.querySelectorAll('.mce-wordcount');
        if (word_counts.length > 0) {
            clearInterval(word_count_interval);
        }
        word_counts.forEach((el) => {
            observer.observe(el, observer_options);
        });
    }

    word_count_interval = setInterval(word_count_alert, 300);

})(jQuery);
