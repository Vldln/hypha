{% load i18n wagtailadmin_tags %}{% base_url_setting as base_url %}
{% blocktrans %}Hello, {% endblocktrans %}

{% blocktrans %}Thank you for registering an account on eQualitie's Grant Programs & Opportunities application system. Please complete your account creation by clicking the link below or copying and pasting it into your browser:
{% endblocktrans %}

{% if site %}{{ site.root_url }}{% else %}{{ base_url }}{% endif %}{{ signup_path }}

{% blocktrans %}This link is valid for {{ timeout_minutes }} minutes and can be used only once.{% endblocktrans %}

{% blocktrans %}If you did not request this email, please ignore it.{% endblocktrans %}

{% if org_email %}
{% blocktrans %}For any questions or concerns, feel free to contact us at {{ org_email }}.{% endblocktrans %}
{% endif %}

{% blocktrans %}Kind regards,{% endblocktrans %}

--
{{ org_long_name }}
https://equalit.ie
