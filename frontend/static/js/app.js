"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {
  tokens: null,
  user: null,
  rooms: [],
  availability: [],
  search: null,
  selected: null,
  refreshPromise: null,
  afterAuth: null,
  authMode: "login",
  searchVersion: 0,
  hotel: {
    timezone: "Europe/Warsaw",
    arrival_windows: [
      "14:00-16:00",
      "16:00-18:00",
      "18:00-20:00",
      "20:00-22:00",
    ],
  },
};
const photoList = [
  ["lounge", "The Willow lounge"],
  ["classic", "The Classic collection"],
  ["deluxe", "The Deluxe collection"],
  ["family", "The Family collection"],
  ["dining", "The Willow table"],
  ["pool", "A moment of calm"],
];
const roomPhotos = { Classic: "classic", Deluxe: "deluxe", Family: "family" };
const money = (value, currency = "PLN") =>
  new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    maximumFractionDigits: value % 100 ? 2 : 0,
  }).format(value / 100);
const prettyDate = (value) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value + "T12:00:00Z"));
const addDays = (value, days) => {
  const date = new Date(value + "T12:00:00Z");
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
};
const today = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: state.hotel.timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function button(text, className, handler) {
  const element = node("button", className, text);
  element.type = "button";
  element.addEventListener("click", handler);
  return element;
}

function roomImage(name) {
  const image = node("img");
  image.src = `/static/images/${roomPhotos[name] || "classic"}.jpg`;
  image.alt = `${name} room`;
  return image;
}

function setTokens(tokens) {
  state.tokens = tokens;
  try {
    if (tokens)
      sessionStorage.setItem("willow.session", JSON.stringify(tokens));
    else sessionStorage.removeItem("willow.session");
  } catch {
    /* The current page still works if browser storage is unavailable. */
  }
}

try {
  const saved = JSON.parse(sessionStorage.getItem("willow.session"));
  if (
    saved &&
    typeof saved.access_token === "string" &&
    typeof saved.refresh_token === "string"
  )
    state.tokens = saved;
} catch {
  setTokens(null);
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function rawRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      method: options.method || "GET",
      cache: "no-store",
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(
      "We could not connect. Please check your connection and try again.",
      0,
    );
  }
  const data =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg.replace(/^Value error, /, "")).join(". ")
      : typeof detail === "string"
        ? detail
        : "Something went wrong. Please try again.";
    throw new ApiError(message, response.status);
  }
  return data;
}

async function refreshSession() {
  if (!state.tokens) throw new ApiError("Please sign in to continue.", 401);
  if (!state.refreshPromise) {
    state.refreshPromise = rawRequest("/auth/refresh", {
      method: "POST",
      body: { refresh_token: state.tokens.refresh_token },
    })
      .then((tokens) => {
        setTokens(tokens);
        return tokens;
      })
      .catch((error) => {
        if (error.status === 401) {
          setTokens(null);
          state.user = null;
          updateAccountLabel();
        }
        throw error;
      })
      .finally(() => {
        state.refreshPromise = null;
      });
  }
  return state.refreshPromise;
}

async function api(path, options = {}) {
  const authorized = options.auth !== false;
  try {
    return await rawRequest(path, {
      ...options,
      token: authorized ? state.tokens?.access_token : null,
    });
  } catch (error) {
    if (error.status !== 401 || !authorized || !state.tokens) throw error;
    const tokens = await refreshSession();
    return rawRequest(path, { ...options, token: tokens.access_token });
  }
}

function message(id, text, success = false) {
  const element = $(id);
  element.textContent = text;
  element.classList.toggle("success", success);
}

let toastTimer;
function toast(text) {
  clearTimeout(toastTimer);
  $("#toast").textContent = text;
  $("#toast").classList.add("visible");
  toastTimer = setTimeout(() => $("#toast").classList.remove("visible"), 4500);
}

function showDialog(id) {
  const dialog = $(id);
  if (!dialog.open) dialog.showModal();
}

$$("dialog").forEach((dialog) => {
  $("[data-close]", dialog).addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    const rect = dialog.getBoundingClientRect();
    if (
      event.target === dialog &&
      (event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom)
    )
      dialog.close();
  });
});

function updateAccountLabel() {
  $$(".account-label").forEach((label) => {
    label.textContent = state.user ? "My stays" : "Your stay";
  });
}

function configureAuth(mode) {
  state.authMode = mode;
  const register = mode === "register";
  $("#auth-title").textContent = register
    ? "Your stay starts here."
    : "Welcome back.";
  $("#auth-description").textContent = register
    ? "Create an account and make room for a little escape."
    : "Sign in to plan a stay or revisit your reservations.";
  $("#full-name-field").hidden = !register;
  $('[name="full_name"]', $("#auth-form")).required = register;
  $('[name="password"]', $("#auth-form")).autocomplete = register
    ? "new-password"
    : "current-password";
  $("#auth-submit").textContent = register ? "Create account" : "Sign in";
  $("#auth-switch-copy").textContent = register
    ? "Already at home here?"
    : "New to Willow?";
  $("#auth-switch").textContent = register ? "Sign in" : "Create an account";
  message("#auth-message", "");
}

function showAuth(afterSuccess) {
  state.afterAuth = afterSuccess || openAccount;
  configureAuth("login");
  showDialog("#auth-dialog");
}

$("#auth-switch").addEventListener("click", () =>
  configureAuth(state.authMode === "login" ? "register" : "login"),
);
$("#auth-dialog").addEventListener("close", () => {
  state.afterAuth = null;
  $("#auth-form").reset();
});
$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const submit = $("#auth-submit");
  submit.disabled = true;
  $("#auth-switch").disabled = true;
  const email = form.elements.email.value;
  const password = form.elements.password.value;
  const register = state.authMode === "register";
  message(
    "#auth-message",
    register ? "Creating your account…" : "Signing you in…",
    true,
  );
  try {
    if (register) {
      await api("/auth/register", {
        method: "POST",
        auth: false,
        body: { email, password, full_name: form.elements.full_name.value },
      });
      configureAuth("login");
    }
    const tokens = await api("/auth/login", {
      method: "POST",
      auth: false,
      body: { email, password },
    });
    setTokens(tokens);
    state.user = await api("/auth/me");
    updateAccountLabel();
    const afterSuccess = state.afterAuth;
    $("#auth-dialog").close();
    toast(
      register
        ? "Welcome to Willow. Your account is ready."
        : "Welcome back to Willow.",
    );
    if (afterSuccess) await afterSuccess();
  } catch (error) {
    message("#auth-message", error.message);
  } finally {
    submit.disabled = false;
    $("#auth-switch").disabled = false;
  }
});

function setDateLimits() {
  const checkIn = $("#check-in");
  const checkOut = $("#check-out");
  checkIn.min = today();
  if (checkIn.value) {
    checkOut.min = addDays(checkIn.value, 1);
    checkOut.max = addDays(checkIn.value, 30);
    if (!checkOut.value || checkOut.value <= checkIn.value)
      checkOut.value = addDays(checkIn.value, 1);
    if (checkOut.value > checkOut.max) checkOut.value = checkOut.max;
  }
}

$("#check-in").value = addDays(today(), 7);
$("#check-out").value = addDays(today(), 9);
setDateLimits();
$("#check-in").addEventListener("change", setDateLimits);

function focusSearch() {
  closeMenu();
  $("#find-a-room").scrollIntoView({
    behavior: reducedMotion.matches ? "instant" : "smooth",
    block: "center",
  });
  $("#check-in").focus({ preventScroll: true });
}

$$("[data-book]").forEach((control) =>
  control.addEventListener("click", focusSearch),
);
$$("[data-room]").forEach((control) =>
  control.addEventListener("click", () => searchRooms(control.dataset.room)),
);
$("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  searchRooms();
});

function changeDatesButton() {
  return button("← Change dates", "back-link", () => {
    $("#reservation-dialog").close();
    focusSearch();
  });
}

async function searchRooms(preferredRoom) {
  setDateLimits();
  if (!$("#search-form").reportValidity()) {
    focusSearch();
    return;
  }
  const search = {
    check_in: $("#check-in").value,
    check_out: $("#check-out").value,
    guests: Number($("#guests").value),
  };
  const version = ++state.searchVersion;
  state.search = search;
  state.selected = null;
  $("#reservation-title").textContent = "Find your little retreat.";
  $("#reservation-dates").textContent =
    `${prettyDate(search.check_in)} — ${prettyDate(search.check_out)} · ${search.guests} ${search.guests === 1 ? "guest" : "guests"}`;
  $("#reservation-content").replaceChildren(
    node("p", "loading-message", "Finding a place for you…"),
  );
  message("#reservation-message", "");
  showDialog("#reservation-dialog");
  try {
    const availability = await api(
      `/availability?${new URLSearchParams(search)}`,
      { auth: false },
    );
    if (version !== state.searchVersion) return;
    state.availability = availability;
    const preferred = availability.find(
      (item) =>
        item.room_type.name === preferredRoom && item.available_rooms > 0,
    );
    if (preferred) {
      state.selected = preferred;
      renderReservation();
    } else renderChoices();
  } catch (error) {
    if (version !== state.searchVersion) return;
    $("#reservation-content").replaceChildren(
      changeDatesButton(),
      button("Try again", "button button-blue", () =>
        searchRooms(preferredRoom),
      ),
    );
    message("#reservation-message", error.message);
  }
}

function renderChoices() {
  $("#reservation-title").textContent = "Choose your room.";
  message("#reservation-message", "");
  const list = node("div", "availability-list");
  for (const item of state.availability) {
    const room = item.room_type;
    const soldOut = item.available_rooms === 0;
    const card = node(
      "article",
      `availability-card${soldOut ? " sold-out" : ""}`,
    );
    const copy = node("div");
    copy.append(
      node("h3", "", room.name),
      node(
        "p",
        "",
        `Up to ${room.capacity} guests · ${soldOut ? "No availability" : `${item.available_rooms} rooms available`}`,
      ),
      node("p", "availability-price", money(item.total_price, room.currency)),
      node(
        "p",
        "",
        `Total for ${item.nights} ${item.nights === 1 ? "night" : "nights"}`,
      ),
    );
    const choose = button(
      soldOut ? "Unavailable" : "Choose room →",
      "button button-blue",
      () => {
        state.selected = item;
        renderReservation();
      },
    );
    choose.disabled = soldOut;
    card.append(roomImage(room.name), copy, choose);
    list.append(card);
  }
  if (!state.availability.length)
    list.append(
      node(
        "p",
        "empty-state",
        "No rooms match this party size. Please try a different number of guests.",
      ),
    );
  $("#reservation-content").replaceChildren(
    changeDatesButton(),
    list,
    node(
      "p",
      "dialog-help",
      "Your room is reserved only after confirmation. All prices are for the full stay.",
    ),
  );
}

function renderReservation() {
  const item = state.selected;
  if (!item) return renderChoices();
  message("#reservation-message", "");
  $("#reservation-title").textContent = "Make it your own.";
  const content = $("#reservation-content");
  const summary = node("div", "reservation-summary");
  const copy = node("div");
  copy.append(
    node("h3", "", `${item.room_type.name} room`),
    node(
      "p",
      "",
      `${item.nights} ${item.nights === 1 ? "night" : "nights"} · ${state.search.guests} ${state.search.guests === 1 ? "guest" : "guests"}`,
    ),
    node("p", "", "A room will be assigned when you confirm."),
  );
  summary.append(roomImage(item.room_type.name), copy);
  const form = node("form");
  form.id = "confirm-booking-form";
  const label = node("label", "", "Your arrival window (Warsaw time)");
  const select = node("select");
  select.name = "arrival_window";
  select.required = true;
  const localTime = new Intl.DateTimeFormat("en-GB", {
    timeZone: state.hotel.timezone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date());
  for (const window of state.hotel.arrival_windows) {
    const option = node("option", "", window.replace("-", " – "));
    option.value = window;
    option.disabled =
      state.search.check_in === today() && window.split("-")[1] <= localTime;
    select.append(option);
  }
  const firstAvailable = [...select.options].find((option) => !option.disabled);
  if (firstAvailable) select.value = firstAvailable.value;
  label.append(select);
  const total = node("div", "price-summary");
  const totalCopy = node("div");
  totalCopy.append(
    node("div", "", "Your stay, in total"),
    node("small", "", "For your selected dates."),
  );
  total.append(
    totalCopy,
    node("strong", "", money(item.total_price, item.room_type.currency)),
  );
  const submit = node(
    "button",
    "button button-dark full-width",
    state.user ? "Confirm reservation" : "Sign in to reserve",
  );
  submit.type = "submit";
  submit.disabled = !firstAvailable;
  form.append(
    label,
    total,
    submit,
    node(
      "p",
      "dialog-help",
      state.user
        ? `Booking as ${state.user.full_name}. Free cancellation before your arrival window begins. Check-out at 11:00.`
        : "Create an account or sign in to keep all your reservations in one place.",
    ),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    if (!state.user) {
      showAuth(renderReservation);
      return;
    }
    submit.disabled = true;
    submit.textContent = "Reserving your room…";
    message("#reservation-message", "");
    try {
      const booking = await api("/bookings", {
        method: "POST",
        body: {
          ...state.search,
          room_type_id: item.room_type.id,
          arrival_window: select.value,
        },
      });
      renderConfirmation(booking, item.room_type.name);
    } catch (error) {
      if (error.status === 401) {
        state.user = null;
        showAuth(renderReservation);
      }
      message(
        "#reservation-message",
        error.status === 0
          ? "The connection was interrupted. Check Your stay before trying to reserve again."
          : error.message,
      );
      submit.disabled = false;
      submit.textContent = state.user
        ? "Confirm reservation"
        : "Sign in to reserve";
      if (error.status === 409)
        content.append(
          button("Check current availability", "text-link", () =>
            searchRooms(),
          ),
        );
    }
  });
  content.replaceChildren(
    button("← All available rooms", "back-link", renderChoices),
    summary,
    form,
  );
  if (!firstAvailable)
    message(
      "#reservation-message",
      "Today's arrival windows have ended. Please choose a later check-in date.",
    );
}

function renderConfirmation(booking, roomName) {
  $("#reservation-title").textContent = "We have a place for you.";
  const panel = node("div", "success-panel");
  const check = node("div", "success-icon", "✓");
  const details = node("div", "success-details");
  details.append(
    node("p", "", `${roomName} · Room ${booking.room.number}`),
    node(
      "p",
      "",
      `${prettyDate(booking.check_in)} — ${prettyDate(booking.check_out)}`,
    ),
    node("p", "", `Arrival: ${booking.arrival_window} · Check-out: 11:00`),
    node("p", "", `Total: ${money(booking.total_price, booking.currency)}`),
  );
  panel.append(
    check,
    node("p", "", "Your reservation is confirmed. A little calm is waiting."),
    details,
    button("View my stays", "button button-dark", () => {
      $("#reservation-dialog").close();
      openAccount();
    }),
  );
  $("#reservation-content").replaceChildren(panel);
  message("#reservation-message", "");
  $("#reservation-title").focus();
}

async function openAccount() {
  if (!state.tokens) {
    showAuth(openAccount);
    return;
  }
  showDialog("#account-dialog");
  $("#account-content").replaceChildren(
    node("p", "loading-message", "A moment, we're finding your stays…"),
  );
  message("#account-message", "");
  try {
    if (!state.user) state.user = await api("/auth/me");
    updateAccountLabel();
    $("#account-greeting").textContent =
      `Welcome, ${state.user.full_name}. A little time away, all in one place.`;
    const bookings = await api("/bookings");
    renderBookings(bookings);
  } catch (error) {
    $("#account-content").replaceChildren();
    if (error.status === 401) {
      $("#account-dialog").close();
      showAuth(openAccount);
    } else {
      message("#account-message", error.message);
      $("#account-content").append(
        button("Try again", "button button-blue", openAccount),
      );
    }
  }
}

function renderBookings(bookings) {
  const content = $("#account-content");
  content.replaceChildren();
  if (!bookings.length) {
    const empty = node("div", "empty-state");
    empty.append(
      node("p", "", "Your next chapter is still unwritten."),
      button("Find your first stay", "button button-blue", () => {
        $("#account-dialog").close();
        focusSearch();
      }),
    );
    content.append(empty);
  }
  for (const booking of bookings) {
    const roomType = state.rooms.find(
      (room) => room.id === booking.room.room_type_id,
    );
    const card = node("article", "booking-item");
    const heading = node("div", "booking-item-header");
    heading.append(
      node(
        "h3",
        "",
        `${roomType?.name || "Your"} room · ${booking.room.number}`,
      ),
      node("span", `status-tag ${booking.status}`, booking.status),
    );
    card.append(
      heading,
      node(
        "p",
        "",
        `${prettyDate(booking.check_in)} — ${prettyDate(booking.check_out)}`,
      ),
      node(
        "p",
        "",
        `${booking.guests} ${booking.guests === 1 ? "guest" : "guests"} · Arrival ${booking.arrival_window} · Check-out 11:00`,
      ),
      node("p", "", `Total ${money(booking.total_price, booking.currency)}`),
    );
    if (booking.status === "confirmed") {
      const cancel = button("Cancel reservation", "text-link", () => {
        cancel.hidden = true;
        const confirmation = node("div", "cancel-confirmation");
        const confirm = button(
          "Confirm cancellation",
          "button button-dark",
          async () => {
            confirm.disabled = true;
            message("#account-message", "");
            try {
              await api(`/bookings/${booking.id}/cancel`, { method: "POST" });
              toast("Your reservation has been cancelled.");
              await openAccount();
            } catch (error) {
              message("#account-message", error.message);
              confirm.disabled = false;
            }
          },
        );
        confirmation.append(
          node(
            "p",
            "",
            "Cancel this reservation? Your room will become available to other guests.",
          ),
          confirm,
          button("Keep my stay", "button button-outline", () => {
            confirmation.remove();
            cancel.hidden = false;
            cancel.focus();
          }),
        );
        card.append(confirmation);
      });
      card.append(cancel);
    }
    content.append(card);
  }
}

$$(".account-trigger").forEach((control) =>
  control.addEventListener("click", openAccount),
);
$("#logout-button").addEventListener("click", async (event) => {
  const control = event.currentTarget;
  control.disabled = true;
  message("#account-message", "");
  try {
    await api("/auth/logout", { method: "POST" });
  } catch (error) {
    if (error.status !== 401) {
      message(
        "#account-message",
        "We could not sign you out. Please try again when connected.",
      );
      control.disabled = false;
      return;
    }
  }
  setTokens(null);
  state.user = null;
  updateAccountLabel();
  $("#account-dialog").close();
  control.disabled = false;
  toast("You have been signed out.");
});

function closeMenu() {
  $(".nav-shell").classList.remove("open");
  $(".menu-toggle").setAttribute("aria-expanded", "false");
  $(".menu-toggle").setAttribute("aria-label", "Open menu");
}
$(".menu-toggle").addEventListener("click", () => {
  const open = $(".nav-shell").classList.toggle("open");
  $(".menu-toggle").setAttribute("aria-expanded", String(open));
  $(".menu-toggle").setAttribute(
    "aria-label",
    open ? "Close menu" : "Open menu",
  );
});
$$(".main-nav a").forEach((link) => link.addEventListener("click", closeMenu));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeMenu();
});
window.addEventListener(
  "scroll",
  () => $(".site-header").classList.toggle("scrolled", scrollY > 20),
  { passive: true },
);

const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
if ("IntersectionObserver" in window && !reducedMotion.matches) {
  document.body.classList.add("motion-ready");
  const observer = new IntersectionObserver(
    (entries) =>
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      }),
    { threshold: 0.08 },
  );
  $$(".reveal").forEach((element) => observer.observe(element));
}

let slide = 0;
let slidePaused = reducedMotion.matches;
function showSlide(index) {
  slide = (index + 3) % 3;
  $$(".hero-image").forEach((image, i) =>
    image.classList.toggle("active", i === slide),
  );
  $$(".slide-dot").forEach((dot, i) => {
    dot.classList.toggle("active", i === slide);
    dot.setAttribute("aria-pressed", String(i === slide));
  });
  $("#slide-counter").textContent = `0${slide + 1} / 03`;
}
function updatePause() {
  $(".slide-pause").setAttribute(
    "aria-label",
    slidePaused ? "Play slideshow" : "Pause slideshow",
  );
  $(".slide-pause").setAttribute("aria-pressed", String(slidePaused));
  $(".slide-pause").textContent = slidePaused ? "▷" : "Ⅱ";
}
$$("[data-slide]").forEach((control) =>
  control.addEventListener("click", () => {
    showSlide(Number(control.dataset.slide));
    slidePaused = true;
    updatePause();
  }),
);
$(".slide-pause").addEventListener("click", () => {
  slidePaused = !slidePaused;
  updatePause();
});
reducedMotion.addEventListener("change", () => {
  slidePaused = reducedMotion.matches;
  updatePause();
});
setInterval(() => {
  if (
    !slidePaused &&
    !document.hidden &&
    !$(".hero").matches(":hover, :focus-within") &&
    !$("dialog[open]")
  )
    showSlide(slide + 1);
}, 7000);
updatePause();

let galleryIndex = 0;
function showPhoto(index) {
  galleryIndex = (index + photoList.length) % photoList.length;
  const [filename, caption] = photoList[galleryIndex];
  $("#gallery-image").src = `/static/images/${filename}.jpg`;
  $("#gallery-image").alt = caption;
  $("#gallery-caption").textContent =
    `${caption} · ${galleryIndex + 1} / ${photoList.length}`;
}
$$("[data-gallery]").forEach((control) =>
  control.addEventListener("click", () => {
    showPhoto(Number(control.dataset.gallery));
    showDialog("#gallery-dialog");
  }),
);
$("#gallery-prev").addEventListener("click", () => showPhoto(galleryIndex - 1));
$("#gallery-next").addEventListener("click", () => showPhoto(galleryIndex + 1));
$("#gallery-dialog").addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    event.preventDefault();
    showPhoto(galleryIndex + (event.key === "ArrowLeft" ? -1 : 1));
  }
});
$("#year").textContent = new Date().getFullYear();

async function initialize() {
  const [hotelResult, roomResult] = await Promise.allSettled([
    api("/hotel", { auth: false }),
    api("/room-types", { auth: false }),
  ]);
  if (hotelResult.status === "fulfilled") {
    state.hotel = hotelResult.value;
    setDateLimits();
  }
  if (roomResult.status === "fulfilled") {
    state.rooms = roomResult.value;
    $$("[data-price]").forEach((element) => {
      const room = state.rooms.find(
        (item) => item.name === element.dataset.price,
      );
      if (room)
        element.replaceChildren(
          node("strong", "", money(room.price_per_night, room.currency)),
          node("small", "", "per room / per night"),
        );
      else element.textContent = "Check availability";
    });
  } else {
    $$("[data-price]").forEach((element) => {
      element.textContent = "Rates unavailable";
    });
    message(
      "#catalog-status",
      "Live rates are temporarily unavailable. You can try again using Check availability.",
    );
  }
  if (state.tokens) {
    try {
      state.user = await api("/auth/me");
      updateAccountLabel();
    } catch (error) {
      if (error.status === 401) {
        setTokens(null);
        state.user = null;
      }
    }
  }
}
initialize();
