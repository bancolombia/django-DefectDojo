{% extends "notifications/mail/base_email.tpl" %}
{% load i18n %}
{% load static %}

{% url 'view_long_risk_acceptance_details' long_risk_acceptance.id as long_ra_url %}
{% url 'view_product' long_risk_acceptance.product.id as product_url %}

{% block content %}
	{% block header %}
		<h2 style="color: #d9534f;">⏳ {% blocktranslate %}Long-Term Risk Acceptance Expiration Notice{% endblocktranslate %}</h2>
	{% endblock %}

	{% block expiration_message %}
		<br/>
		<div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 15px 0;">
			{% if long_risk_acceptance.expiration_date_handled %}
				{% blocktranslate with expiration_date=long_risk_acceptance.expiration_date_handled|date:"b d, Y H:i" %}
					<strong>This long-term risk acceptance has EXPIRED on {{ expiration_date }}</strong>
				{% endblocktranslate %}
			{% else %}
				{% blocktranslate with expiration_date=long_risk_acceptance.expiration_date|date:"b d, Y H:i" %}
					<strong>This long-term risk acceptance will EXPIRE on {{ expiration_date }}</strong>
				{% endblocktranslate %}
			{% endif %}
		</div>
	{% endblock %}

	{% block description_section %}
		<br/>
		{% if long_risk_acceptance.description %}
			<h3>{% blocktranslate %}Description{% endblocktranslate %}</h3>
			<p>{{ long_risk_acceptance.description }}</p>
		{% endif %}
	{% endblock %}

	{% block findings_count %}
		<br/>
		<h3>{% blocktranslate %}Accepted Findings Count{% endblocktranslate %}</h3>
		<table class="proton-table" style="margin: 15px 0;">
			<tr>
				<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
					{% blocktranslate %}Total Findings:{% endblocktranslate %}
				</td>
				<td style="padding: 10px;">
					<strong style="font-size: 18px; color: #d9534f;">
						{{ findings_count|default:"0" }}
					</strong>
				</td>
			</tr>
		</table>
	{% endblock %}

	{% block critical_dates %}
		<br/>
		<h3>{% blocktranslate %}Critical Dates{% endblocktranslate %}</h3>
		<table class="proton-table" style="margin: 15px 0;">
			{% if long_risk_acceptance.expiration_date %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Expiration Date:{% endblocktranslate %}
					</td>
					<td style="padding: 10px; color: #d9534f; font-weight: bold;">
						{{ long_risk_acceptance.expiration_date|date:"b d, Y H:i" }}
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.expiration_date_warned %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Warning Sent On:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.expiration_date_warned|date:"b d, Y H:i" }}
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.expiration_date_handled %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Handled On:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.expiration_date_handled|date:"b d, Y H:i" }}
					</td>
				</tr>
			{% endif %}
		</table>
	{% endblock %}

	{% block reactivation_info %}
		<br/>
		<h3>{% blocktranslate %}Automatic Actions{% endblocktranslate %}</h3>
		<div style="background-color: #f0f8ff; border-left: 4px solid #0066cc; padding: 15px; margin: 15px 0;">
			{% if long_risk_acceptance.reactivate_expired %}
				<p>{% blocktranslate %}<strong>✓ Findings will be reactivated</strong> when this risk acceptance expires.{% endblocktranslate %}</p>
			{% else %}
				<p>{% blocktranslate %}<strong>✗ Findings will NOT be reactivated</strong> when this risk acceptance expires.{% endblocktranslate %}</p>
			{% endif %}
		</div>
	{% endblock %}

	{% block owner_info %}
		<br/>
		<h3>{% blocktranslate %}Responsible Parties{% endblocktranslate %}</h3>
		<table class="proton-table" style="margin: 15px 0;">
			{% if long_risk_acceptance.owner %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Owner:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.owner.username }}
						{% if long_risk_acceptance.owner.email %}
							({{ long_risk_acceptance.owner.email }})
						{% endif %}
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.reviewed_by %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Reviewed By:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.reviewed_by }}
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.accepted_by %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Accepted By:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{{ long_risk_acceptance.accepted_by.username }}
						{% if long_risk_acceptance.accepted_by.email %}
							({{ long_risk_acceptance.accepted_by.email }})
						{% endif %}
					</td>
				</tr>
			{% endif %}
		</table>
	{% endblock %}

	{% block product_info %}
		<br/>
		<h3>{% blocktranslate %}Product & Engagements{% endblocktranslate %}</h3>
		<table class="proton-table" style="margin: 15px 0;">
			{% if long_risk_acceptance.product %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold;">
						{% blocktranslate %}Product:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						<a href="{{ product_url|full_url }}" style="color: #0066cc; text-decoration: none;">
							{{ long_risk_acceptance.product.name }}
						</a>
					</td>
				</tr>
			{% endif %}
			{% if long_risk_acceptance.engagement_set.all %}
				<tr>
					<td style="padding: 10px; background-color: #f5f5f5; font-weight: bold; vertical-align: top;">
						{% blocktranslate %}Engagements:{% endblocktranslate %}
					</td>
					<td style="padding: 10px;">
						{% for engagement in long_risk_acceptance.engagement_set.all %}
							<div style="margin: 5px 0;">• {{ engagement.name }}</div>
						{% endfor %}
					</td>
				</tr>
			{% endif %}
		</table>
	{% endblock %}

	{% block action_required %}
		<br/>
		<br/>
		<div style="background-color: #f8d7da; border: 2px solid #f5c6cb; border-radius: 5px; padding: 20px; margin: 20px 0; text-align: center;">
			<h3 style="color: #721c24; margin-top: 0;">{% blocktranslate %}⚠️ Action Required{% endblocktranslate %}</h3>
			<p>{% blocktranslate %}Review the details of this risk acceptance and take necessary actions before expiration.{% endblocktranslate %}</p>
			<a href="{{ long_ra_url|full_url }}" class="proton-button" target="_blank" style="display: inline-block; padding: 12px 24px; background-color: #FFC300; color: #333; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 14px; margin-top: 10px;">
				{% blocktranslate %}View Risk Acceptance Details{% endblocktranslate %}
			</a>
		</div>
	{% endblock %}

	{% block footer %}
		<br/>
		<br/>
		<hr style="border: none; border-top: 1px solid #ccc; margin: 20px 0;">
		<p style="font-size: 12px; color: #666; text-align: center;">
			{% blocktranslate %}This is an automated expiration notification from DefectDojo. Do not reply to this email.{% endblocktranslate %}
		</p>
	{% endblock %}
{% endblock %}
