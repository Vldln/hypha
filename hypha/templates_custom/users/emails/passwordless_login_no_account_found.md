{% load i18n wagtailadmin_tags %}{% base_url_setting as base_url %}

{% blocktrans %}Hello,{% endblocktrans %}

{% blocktrans %}It seems you are trying to log in to the {{ org_long_name }}'s Grant Programs & Opportunities website, but we could not find an account associated with the email address provided. Check if you have entered the correct email or create a new account.{% endblocktrans %}

{% if org_email %}
{% blocktrans %}If you have any questions or need assistance, please contact us at {{ org_email }}.{% endblocktrans %}
{% endif %}

{% blocktrans %}Kind Regards,
{% endblocktrans %}

--
{{ org_long_name }}
{% if site %}{{ site.root_url }}{% else %}{{ base_url }}{% endif %}
