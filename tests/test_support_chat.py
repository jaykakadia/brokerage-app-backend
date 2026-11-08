def _login(client, user, password):
    client.post("/api/v1/auth/login", json={"email": user.email, "password": password})


def test_support_chat_full_flow(client, admin_user, test_user):
    # 1. Guest visitor tries to init without contact info -> fails
    res_bad = client.post("/api/v1/support/conversations/init", json={})
    assert res_bad.status_code == 400

    # 2. Guest visitor provides contact info -> creates conversation with welcome message
    guest_init = client.post("/api/v1/support/conversations/init", json={
        "name": "Aman Sharma",
        "email": "aman@example.com",
        "phone": "9876543210"
    })
    assert guest_init.status_code == 200, guest_init.text
    data = guest_init.json()["data"]
    session_id = data["session_id"]
    conv_id = data["id"]
    assert data["display_name"] == "Aman Sharma"
    assert data["display_email"] == "aman@example.com"
    assert data["status"] == "open"
    # Should have the automatic bot welcome message
    assert len(data["messages"]) == 1
    assert data["messages"][0]["sender_type"] == "bot"

    # 3. Guest sends a message
    res_msg = client.post(f"/api/v1/support/conversations/{session_id}/messages", json={
        "message": "Hi, I need help with listing ID 101."
    })
    assert res_msg.status_code == 200
    msg_id = res_msg.json()["data"]["id"]

    # 4. Polling fallback returns the message
    poll_res = client.get(f"/api/v1/support/conversations/{session_id}/poll?after_id=0")
    assert poll_res.status_code == 200
    assert len(poll_res.json()["data"]) >= 2  # Bot message + guest message

    # 5. Admin lists conversations and sees the unread thread
    # Unauthenticated admin access rejected
    assert client.get("/api/v1/admin/support/conversations").status_code == 401

    _login(client, admin_user, "adminpass123")
    admin_list = client.get("/api/v1/admin/support/conversations").json()["data"]
    assert admin_list["total"] >= 1
    assert admin_list["counts"]["unread_total"] >= 1

    # 6. Admin opens conversation detail (resets unread_admin_count)
    admin_detail = client.get(f"/api/v1/admin/support/conversations/{conv_id}").json()["data"]
    assert admin_detail["unread_admin_count"] == 0
    assert len(admin_detail["messages"]) >= 2

    # 7. Admin replies to guest
    admin_reply = client.post(f"/api/v1/admin/support/conversations/{conv_id}/messages", json={
        "message": "Sure Aman, let me check the status of listing 101 for you."
    })
    assert admin_reply.status_code == 200
    assert admin_reply.json()["data"]["sender_type"] == "admin"

    # 8. Visitor checks conversation and sees admin reply
    visitor_check = client.get(f"/api/v1/support/conversations/{session_id}").json()["data"]
    last_msg = visitor_check["messages"][-1]
    assert last_msg["sender_type"] == "admin"
    assert "Sure Aman" in last_msg["message"]

    # 9. Admin updates status to resolved
    status_res = client.patch(f"/api/v1/admin/support/conversations/{conv_id}/status", json={
        "status": "resolved"
    })
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "success"

    # Visitor and Admin cannot send messages while ticket is resolved
    res_resolved_visitor = client.post(f"/api/v1/support/conversations/{session_id}/messages", json={
        "message": "Can I still ask a question?"
    })
    assert res_resolved_visitor.status_code == 400
    assert "resolved" in res_resolved_visitor.json()["detail"]

    res_resolved_admin = client.post(f"/api/v1/admin/support/conversations/{conv_id}/messages", json={
        "message": "Admin message on resolved ticket"
    })
    assert res_resolved_admin.status_code == 400
    assert "resolved" in res_resolved_admin.json()["detail"]

    # 10. Signed-in user initializes chat -> automatically binds user info without contact form
    client.post("/api/v1/auth/logout")
    _login(client, test_user, "password123")
    user_init = client.post("/api/v1/support/conversations/init", json={})
    assert user_init.status_code == 200
    u_data = user_init.json()["data"]
    assert u_data["user_id"] == test_user.id
    assert u_data["display_name"] == test_user.name
    assert u_data["is_registered_user"] is True

    # 11. User lists their tickets (logged-in user sees their tickets automatically)
    my_tickets = client.get(f"/api/v1/support/conversations/my-tickets?session_ids={session_id}").json()["data"]
    assert len(my_tickets) >= 2

    # Logged-in user queries without session_ids -> returns their user tickets
    user_tickets_only = client.get("/api/v1/support/conversations/my-tickets").json()["data"]
    assert len(user_tickets_only) >= 1
    assert any(t["session_id"] == u_data["session_id"] for t in user_tickets_only)

    # Guest queries by same name and phone number -> returns matching tickets
    client.post("/api/v1/auth/logout")
    guest_name_phone_tickets = client.get(
        "/api/v1/support/conversations/my-tickets?name=Aman%20Sharma&phone=9876543210"
    ).json()["data"]
    assert len(guest_name_phone_tickets) >= 1
    assert any(t["session_id"] == session_id for t in guest_name_phone_tickets)

    # 12. Close ticket and verify cannot send message, then verify reopen endpoint
    _login(client, admin_user, "adminpass123")
    close_res = client.patch(f"/api/v1/admin/support/conversations/{conv_id}/status", json={"status": "closed"})
    assert close_res.status_code == 200

    # Verify admin list can filter by closed and counts include closed
    list_closed_res = client.get("/api/v1/admin/support/conversations?status=closed")
    assert list_closed_res.status_code == 200
    closed_data = list_closed_res.json()["data"]
    assert closed_data["counts"]["closed"] >= 1
    assert any(c["id"] == conv_id for c in closed_data["items"])

    # Visitor cannot send message while ticket is closed
    res_closed_visitor = client.post(f"/api/v1/support/conversations/{session_id}/messages", json={
        "message": "Trying to message closed ticket"
    })
    assert res_closed_visitor.status_code == 400
    assert "closed" in res_closed_visitor.json()["detail"]

    # Admin cannot send message while ticket is closed
    res_closed_admin = client.post(f"/api/v1/admin/support/conversations/{conv_id}/messages", json={
        "message": "Admin message on closed ticket"
    })
    assert res_closed_admin.status_code == 400
    assert "closed" in res_closed_admin.json()["detail"]

    client.post("/api/v1/auth/logout")
    reopen_res = client.post(f"/api/v1/support/conversations/{session_id}/reopen")
    assert reopen_res.status_code == 200
    assert reopen_res.json()["data"]["status"] == "open"

    # Now visitor can send messages again
    res_reopened_msg = client.post(f"/api/v1/support/conversations/{session_id}/messages", json={
        "message": "I am back with another question!"
    })
    assert res_reopened_msg.status_code == 200

    # 13. Visitor uploads an image
    dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    upload_res = client.post(
        "/api/v1/support/upload",
        data={"session_id": session_id, "message": "Here is my screenshot"},
        files={"file": ("screenshot.png", dummy_png, "image/png")}
    )
    assert upload_res.status_code == 200, upload_res.text
    upload_data = upload_res.json()["data"]
    assert upload_data["attachment_url"] is not None
    assert upload_data["attachment_url"].startswith("/uploads/support_chat/")
    assert upload_data["message"] == "Here is my screenshot"

    # 14. Admin uploads an image in reply
    _login(client, admin_user, "adminpass123")
    admin_upload_res = client.post(
        f"/api/v1/admin/support/conversations/{conv_id}/upload",
        data={"message": "Here is the solution screenshot"},
        files={"file": ("solution.png", dummy_png, "image/png")}
    )
    assert admin_upload_res.status_code == 200, admin_upload_res.text
    admin_upload_data = admin_upload_res.json()["data"]
    assert admin_upload_data["attachment_url"] is not None
    assert admin_upload_data["attachment_url"].startswith("/uploads/support_chat/")
    assert admin_upload_data["sender_type"] == "admin"

