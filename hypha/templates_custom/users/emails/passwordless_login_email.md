{% load i18n wagtailadmin_tags %}{% base_url_setting as base_url %}{% firstof name username as user %}
{% blocktrans %}Dear {{ user }},{% endblocktrans %}

{% if is_active %}
{% blocktrans %}Login to your account on the eQualitie's *Grant Programs & Opportunities application system by clicking the link below or copying and pasting it into your browser:{% endblocktrans %}

{% if site %}{{ site.root_url }}{% else %}{{ base_url }}{% endif %}{{ login_path }}

{% blocktrans %}This link will be valid for {{ timeout_minutes }} minutes and can be used only once.{% endblocktrans %}

{% else %}
{% blocktrans %}Your account on the {{ org_long_name }}s Grant Programs & Opportunities website has been deactivated. Create a new account or contact the site administrators for assistance.
{% endblocktrans %}
{% endif %}

{% blocktrans %}If you did not request this email, please ignore it.{% endblocktrans %}

{% if org_email %}
{% blocktrans %}For any questions or concerns, please contact us at {{ org_email }}.{% endblocktrans %}
{% endif %}

{% blocktrans %}Kind regards,{% endblocktrans %}

--
{{ org_long_name }}
https://equalit.ie
