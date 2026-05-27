"""AgentDojo suite-specific tool implementations.

Framework role:
- Provides banking and travel tool implementations for AgentDojo benchmarks.
- Ported from the AgentDojo reference as plain functions with explicit state arguments.

Runtime/usage wiring:
- Used by StatefulToolExecutor as default implementations when suite is "banking" or "travel".

Change guardrails:
- Tool implementations must match the behavior of the AgentDojo reference
  exactly for benchmark comparability.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Banking tool implementations
# ---------------------------------------------------------------------------


def _next_transaction_id(state: dict[str, Any]) -> int:
    acct = state["bank_account"]
    ids = [t["id"] for t in acct.get("transactions", [])] + [t["id"] for t in acct.get("scheduled_transactions", [])]
    return (max(ids, default=0)) + 1


def _banking_get_balance(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return {"balance": state["bank_account"]["balance"]}


def _banking_get_iban(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return {"IBAN": state["bank_account"]["iban"]}


def _banking_get_most_recent_transactions(state: dict[str, Any], *, n: int = 100, **kwargs: Any) -> dict[str, Any]:
    txns = state["bank_account"].get("transactions", [])
    return {"transactions": txns[-int(n):]}


def _banking_get_scheduled_transactions(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return {"scheduled_transactions": state["bank_account"].get("scheduled_transactions", [])}


def _banking_send_money(
    state: dict[str, Any],
    *,
    recipient: str,
    amount: float,
    subject: str,
    date: str,
    **kwargs: Any,
) -> dict[str, Any]:
    acct = state["bank_account"]
    txn = {
        "id": _next_transaction_id(state),
        "sender": acct["iban"],
        "recipient": recipient,
        "amount": amount,
        "subject": subject,
        "date": date,
        "recurring": False,
    }
    acct["transactions"].append(txn)
    return {"message": f"Transaction to {recipient} for {amount} sent."}


def _banking_schedule_transaction(
    state: dict[str, Any],
    *,
    recipient: str,
    amount: float,
    subject: str,
    date: str,
    recurring: bool,
    **kwargs: Any,
) -> dict[str, Any]:
    acct = state["bank_account"]
    txn = {
        "id": _next_transaction_id(state),
        "sender": acct["iban"],
        "recipient": recipient,
        "amount": amount,
        "subject": subject,
        "date": date,
        "recurring": recurring,
    }
    acct["scheduled_transactions"].append(txn)
    return {"message": f"Transaction to {recipient} for {amount} scheduled."}


def _banking_update_scheduled_transaction(
    state: dict[str, Any],
    *,
    id: int,
    recipient: str | None = None,
    amount: float | None = None,
    subject: str | None = None,
    date: str | None = None,
    recurring: bool | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    acct = state["bank_account"]
    txn = next((t for t in acct["scheduled_transactions"] if t["id"] == id), None)
    if txn is None:
        return {"error": f"Transaction with ID {id} not found."}
    if recipient is not None:
        txn["recipient"] = recipient
    if amount is not None:
        txn["amount"] = amount
    if subject is not None:
        txn["subject"] = subject
    if date is not None:
        txn["date"] = date
    if recurring is not None:
        txn["recurring"] = recurring
    return {"message": f"Transaction with ID {id} updated."}


def _banking_read_file(
    state: dict[str, Any],
    *,
    file_path: str | None = None,
    filename: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    filename = file_path if file_path is not None else filename
    if filename is None:
        return {"error": "Missing file_path."}
    fs = state.get("filesystem", {})
    files = fs.get("files", {})
    if filename in files:
        return {"content": files[filename]}
    return {"error": f"File '{filename}' not found."}


def _banking_get_user_info(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    ua = state.get("user_account", {})
    return {k: v for k, v in ua.items() if k != "password"}


def _banking_update_password(state: dict[str, Any], *, password: str, **kwargs: Any) -> dict[str, Any]:
    state["user_account"]["password"] = password
    return {"message": "Password updated."}


def _banking_update_user_info(
    state: dict[str, Any],
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    street: str | None = None,
    city: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    ua = state["user_account"]
    if first_name is not None:
        ua["first_name"] = first_name
    if last_name is not None:
        ua["last_name"] = last_name
    if street is not None:
        ua["street"] = street
    if city is not None:
        ua["city"] = city
    return {"message": "User info updated."}


BANKING_TOOLS: dict[str, Callable] = {
    "get_balance": _banking_get_balance,
    "get_iban": _banking_get_iban,
    "get_most_recent_transactions": _banking_get_most_recent_transactions,
    "get_scheduled_transactions": _banking_get_scheduled_transactions,
    "send_money": _banking_send_money,
    "schedule_transaction": _banking_schedule_transaction,
    "update_scheduled_transaction": _banking_update_scheduled_transaction,
    "read_file": _banking_read_file,
    "get_user_info": _banking_get_user_info,
    "update_password": _banking_update_password,
    "update_user_info": _banking_update_user_info,
}


# ---------------------------------------------------------------------------
# Travel tool implementations
# ---------------------------------------------------------------------------


def _travel_get_user_information(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    user = state.get("user", {})
    return {k: v for k, v in user.items()}


def _travel_get_all_hotels_in_city(state: dict[str, Any], *, city: str, **kwargs: Any) -> dict[str, Any]:
    hotels = state.get("hotels", {}).get("hotel_list", [])
    names = [h["name"] for h in hotels if h.get("city") == city]
    return {"hotels": names}


def _travel_get_hotels_prices(state: dict[str, Any], *, hotel_names: list[str], **kwargs: Any) -> dict[str, Any]:
    hotels = state.get("hotels", {}).get("hotel_list", [])
    return {
        h["name"]: f"Price range: {h['price_min']} - {h['price_max']}"
        for h in hotels
        if h["name"] in hotel_names
    }


def _travel_get_hotels_address(state: dict[str, Any], *, hotel_name: str, **kwargs: Any) -> dict[str, Any]:
    hotels = state.get("hotels", {}).get("hotel_list", [])
    return {h["name"]: h["address"] for h in hotels if h["name"] == hotel_name}


def _travel_get_rating_reviews_for_hotels(
    state: dict[str, Any], *, hotel_names: list[str], **kwargs: Any
) -> dict[str, Any]:
    hotels = state.get("hotels", {}).get("hotel_list", [])
    return {
        h["name"]: f"Rating: {h['rating']}\nReviews: " + "\n".join(h.get("reviews", []))
        for h in hotels
        if h["name"] in hotel_names
    }


def _travel_get_all_restaurants_in_city(
    state: dict[str, Any], *, city: str, **kwargs: Any
) -> dict[str, Any]:
    restaurants = state.get("restaurants", {}).get("restaurant_list", [])
    names = [r["name"] for r in restaurants if r.get("city") == city]
    return {"restaurants": names}


def _travel_get_restaurants_address(
    state: dict[str, Any], *, restaurant_names: list[str], **kwargs: Any
) -> dict[str, Any]:
    restaurants = state.get("restaurants", {}).get("restaurant_list", [])
    return {r["name"]: r["address"] for r in restaurants if r["name"] in restaurant_names}


def _travel_get_rating_reviews_for_restaurants(
    state: dict[str, Any], *, restaurant_names: list[str], **kwargs: Any
) -> dict[str, Any]:
    restaurants = state.get("restaurants", {}).get("restaurant_list", [])
    return {
        r["name"]: f"Rating: {r['rating']}\nReviews: " + "\n".join(r.get("reviews", []))
        for r in restaurants
        if r["name"] in restaurant_names
    }


def _travel_get_dietary_restrictions_for_all_restaurants(
    state: dict[str, Any], *, restaurant_names: list[str], **kwargs: Any
) -> dict[str, Any]:
    restaurants = state.get("restaurants", {}).get("restaurant_list", [])
    restaurant_names_text = ", ".join(restaurant_names)
    return {
        r["name"]: r.get("dietary_restrictions", "")
        for r in restaurants
        if r["name"] in restaurant_names_text
    }


def _travel_get_contact_information_for_restaurants(
    state: dict[str, Any], *, restaurant_names: list[str], **kwargs: Any
) -> dict[str, Any]:
    restaurants = state.get("restaurants", {}).get("restaurant_list", [])
    return {
        r["name"]: r.get("contact_information", "")
        for r in restaurants
        if r["name"] in restaurant_names
    }


def _travel_get_cuisine_type_for_restaurants(
    state: dict[str, Any], *, restaurant_names: list[str], **kwargs: Any
) -> dict[str, Any]:
    restaurants = state.get("restaurants", {}).get("restaurant_list", [])
    return {r["name"]: r.get("cuisine_type", "") for r in restaurants if r["name"] in restaurant_names}


def _travel_get_price_for_restaurants(
    state: dict[str, Any], *, restaurant_names: list[str], **kwargs: Any
) -> dict[str, Any]:
    restaurants = state.get("restaurants", {}).get("restaurant_list", [])
    return {r["name"]: r.get("price_per_person", 0) for r in restaurants if r["name"] in restaurant_names}


def _travel_check_restaurant_opening_hours(
    state: dict[str, Any], *, restaurant_names: list[str], **kwargs: Any
) -> dict[str, Any]:
    restaurants = state.get("restaurants", {}).get("restaurant_list", [])
    return {r["name"]: r.get("operating_hours", "") for r in restaurants if r["name"] in restaurant_names}


def _travel_get_all_car_rental_companies_in_city(
    state: dict[str, Any], *, city: str, **kwargs: Any
) -> dict[str, Any]:
    companies = state.get("car_rental", {}).get("company_list", [])
    names = [c["name"] for c in companies if c.get("city") == city]
    return {"car_rental_companies": names}


def _travel_get_car_types_available(
    state: dict[str, Any], *, company_name: list[str], **kwargs: Any
) -> dict[str, Any]:
    companies = state.get("car_rental", {}).get("company_list", [])
    return {c["name"]: c.get("car_types_available", []) for c in companies if c["name"] in company_name}


def _travel_get_rating_reviews_for_car_rental(
    state: dict[str, Any], *, company_name: list[str], **kwargs: Any
) -> dict[str, Any]:
    companies = state.get("car_rental", {}).get("company_list", [])
    return {
        c["name"]: f"Rating: {c['rating']}\nReviews: " + "\n".join(c.get("reviews", []))
        for c in companies
        if c["name"] in company_name
    }


def _travel_get_car_rental_address(
    state: dict[str, Any], *, company_name: list[str], **kwargs: Any
) -> dict[str, Any]:
    companies = state.get("car_rental", {}).get("company_list", [])
    return {c["name"]: c.get("address", "") for c in companies if c["name"] in company_name}


def _travel_get_car_fuel_options(
    state: dict[str, Any], *, company_name: list[str], **kwargs: Any
) -> dict[str, Any]:
    companies = state.get("car_rental", {}).get("company_list", [])
    return {c["name"]: c.get("fuel_options", []) for c in companies if c["name"] in company_name}


def _travel_get_car_price_per_day(
    state: dict[str, Any], *, company_name: list[str], **kwargs: Any
) -> dict[str, Any]:
    companies = state.get("car_rental", {}).get("company_list", [])
    return {c["name"]: c.get("price_per_day", 0) for c in companies if c["name"] in company_name}


def _parse_calendar_datetime(value: str) -> datetime.datetime:
    return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M")


def _iso_calendar_datetime(value: datetime.datetime) -> str:
    return value.isoformat(timespec="seconds")


def _next_mapping_id(items: dict[str, Any]) -> str:
    ids: list[int] = []
    for key in items:
        try:
            ids.append(int(key))
        except (TypeError, ValueError):
            continue
    return str(max(ids, default=-1) + 1)


def _refresh_inbox_views(inbox: dict[str, Any]) -> None:
    emails = list(inbox.get("emails", {}).values())
    inbox["received"] = [email for email in emails if email.get("status") == "received"]
    inbox["sent"] = [email for email in emails if email.get("status") == "sent"]
    inbox["drafts"] = [email for email in emails if email.get("status") == "draft"]


def _travel_send_email(
    state: dict[str, Any],
    *,
    recipients: list[str],
    subject: str,
    body: str,
    attachments: list[dict[str, Any]] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    inbox = state.setdefault("inbox", {})
    emails = inbox.setdefault("emails", {})
    email_id = _next_mapping_id(emails)
    email = {
        "id_": email_id,
        "sender": inbox.get("account_email", ""),
        "recipients": recipients,
        "cc": cc or [],
        "bcc": bcc or [],
        "subject": subject,
        "body": body,
        "status": "sent",
        "read": True,
        "timestamp": datetime.datetime.now().isoformat(),
        "attachments": attachments or [],
    }
    emails[email_id] = email
    _refresh_inbox_views(inbox)
    return email


def _travel_create_calendar_event(
    state: dict[str, Any],
    *,
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    participants: list[str] | None = None,
    location: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    calendar = state.setdefault("calendar", {})
    events = calendar.setdefault("events", {})
    event_id = _next_mapping_id(events)
    participants = list(participants or [])
    account_email = calendar.get("account_email")
    if account_email is not None:
        participants.append(account_email)
    participants = list(set(participants))
    event = {
        "id_": event_id,
        "title": title,
        "description": description,
        "start_time": _iso_calendar_datetime(_parse_calendar_datetime(start_time)),
        "end_time": _iso_calendar_datetime(_parse_calendar_datetime(end_time)),
        "location": location,
        "participants": participants,
        "all_day": False,
        "status": "confirmed",
    }
    events[event_id] = event
    _travel_send_email(
        state,
        recipients=participants,
        subject=f"Invitation: {title}",
        body=description,
        attachments=[event],
    )
    return event


def _event_date(event: dict[str, Any]) -> datetime.date:
    return datetime.datetime.fromisoformat(str(event.get("start_time"))).date()


def _travel_get_day_calendar_events(
    state: dict[str, Any], *, day: str, **kwargs: Any
) -> list[dict[str, Any]]:
    target = datetime.datetime.strptime(day, "%Y-%m-%d").date()
    events = state.get("calendar", {}).get("events", {}).values()
    return [event for event in events if _event_date(event) == target]


def _travel_search_calendar_events(
    state: dict[str, Any], *, query: str, date: str | None = None, **kwargs: Any
) -> list[dict[str, Any]]:
    if date is not None:
        events = _travel_get_day_calendar_events(state, day=date)
    else:
        events = list(state.get("calendar", {}).get("events", {}).values())
    query_lower = query.lower()
    matches = [
        event
        for event in events
        if query_lower in str(event.get("title", "")).lower()
        or query_lower in str(event.get("description", "")).lower()
    ]
    if not matches:
        raise ValueError("No events found. Try with a different query.")
    return matches


def _travel_cancel_calendar_event(
    state: dict[str, Any], *, event_id: str, **kwargs: Any
) -> str:
    events = state.get("calendar", {}).get("events", {})
    if event_id not in events:
        raise ValueError(f"Event with ID '{event_id}' not found.")
    event = events[event_id]
    event["status"] = "canceled"
    _travel_send_email(
        state,
        recipients=list(event.get("participants", [])),
        subject=f"Canceled: '{event.get('title', '')}'",
        body="The event has been canceled.",
        attachments=[event],
    )
    return f"Event with ID {event_id} has been canceled and participants have been notified."


def _travel_reserve_hotel(
    state: dict[str, Any],
    *,
    hotel: str,
    start_day: str,
    end_day: str,
    **kwargs: Any,
) -> dict[str, Any]:
    res = state.get("reservation", {})
    user = state.get("user", {})
    res["reservation_type"] = "hotel"
    res["title"] = hotel
    res["start_time"] = start_day
    res["end_time"] = end_day
    res["contact_information"] = user.get("phone_number", "")
    return {"message": f"Reservation for {hotel} from {start_day} to {end_day} has been made successfully."}


def _travel_reserve_restaurant(
    state: dict[str, Any],
    *,
    restaurant: str,
    start_time: str,
    **kwargs: Any,
) -> dict[str, Any]:
    res = state.get("reservation", {})
    user = state.get("user", {})
    res["reservation_type"] = "restaurant"
    res["title"] = restaurant
    res["start_time"] = start_time
    res["contact_information"] = user.get("phone_number", "")
    return {"message": f"Reservation for {restaurant} at {start_time} has been made successfully."}


def _travel_reserve_car_rental(
    state: dict[str, Any],
    *,
    company: str,
    start_time: str,
    end_time: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    res = state.get("reservation", {})
    user = state.get("user", {})
    res["reservation_type"] = "car"
    res["title"] = company
    res["start_time"] = start_time
    res["end_time"] = end_time or start_time
    res["contact_information"] = user.get("phone_number", "")
    return {"message": f"Reservation for a car at {company} from {start_time} has been made successfully."}


def _travel_get_flight_information(
    state: dict[str, Any],
    *,
    departure_city: str,
    arrival_city: str,
    **kwargs: Any,
) -> dict[str, Any]:
    flights = state.get("flights", {}).get("flight_list", [])
    results = []
    for f in flights:
        if f.get("departure_city") == departure_city and f.get("arrival_city") == arrival_city:
            results.append(f)
    return {"flights": results}


TRAVEL_TOOLS: dict[str, Callable] = {
    "get_user_information": _travel_get_user_information,
    "get_all_hotels_in_city": _travel_get_all_hotels_in_city,
    "get_hotels_prices": _travel_get_hotels_prices,
    "get_hotels_address": _travel_get_hotels_address,
    "get_rating_reviews_for_hotels": _travel_get_rating_reviews_for_hotels,
    "get_all_restaurants_in_city": _travel_get_all_restaurants_in_city,
    "get_restaurants_address": _travel_get_restaurants_address,
    "get_rating_reviews_for_restaurants": _travel_get_rating_reviews_for_restaurants,
    "get_dietary_restrictions_for_all_restaurants": _travel_get_dietary_restrictions_for_all_restaurants,
    "get_contact_information_for_restaurants": _travel_get_contact_information_for_restaurants,
    "get_cuisine_type_for_restaurants": _travel_get_cuisine_type_for_restaurants,
    "get_price_for_restaurants": _travel_get_price_for_restaurants,
    "check_restaurant_opening_hours": _travel_check_restaurant_opening_hours,
    "get_all_car_rental_companies_in_city": _travel_get_all_car_rental_companies_in_city,
    "get_car_types_available": _travel_get_car_types_available,
    "get_rating_reviews_for_car_rental": _travel_get_rating_reviews_for_car_rental,
    "get_car_rental_address": _travel_get_car_rental_address,
    "get_car_fuel_options": _travel_get_car_fuel_options,
    "get_car_price_per_day": _travel_get_car_price_per_day,
    "create_calendar_event": _travel_create_calendar_event,
    "search_calendar_events": _travel_search_calendar_events,
    "get_day_calendar_events": _travel_get_day_calendar_events,
    "cancel_calendar_event": _travel_cancel_calendar_event,
    "reserve_hotel": _travel_reserve_hotel,
    "reserve_restaurant": _travel_reserve_restaurant,
    "reserve_car_rental": _travel_reserve_car_rental,
    "get_flight_information": _travel_get_flight_information,
    "send_email": _travel_send_email,
}


SUITE_TOOL_IMPLEMENTATIONS: dict[str, dict[str, Callable]] = {
    "banking": BANKING_TOOLS,
    "travel": TRAVEL_TOOLS,
}
