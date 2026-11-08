"""Laravel snippets: route groups, resources, middleware, controllers, migrations, Blade (T29)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yoriqnoma_scanner.api import scan
from yoriqnoma_scanner.parsers.laravel import laravel_path, split_top

Writer = Callable[[Path, dict[str, str]], Path]

LARAVEL_PROJECT = {
    "composer.json": '{"require": {"php": "^8.2", "laravel/framework": "^11.0"}}',
    "routes/web.php": """<?php
use App\\Http\\Controllers\\Auth\\RegisteredUserController;
use App\\Http\\Controllers\\OrderController;
use App\\Http\\Controllers\\Staff\\StaffOrderController;
use Illuminate\\Support\\Facades\\Route;

Route::get('/', function () {
    return view('welcome');
})->name('home');

Route::middleware('guest')->group(function () {
    Route::get('register', [RegisteredUserController::class, 'create'])->name('register');
    Route::post('register', [RegisteredUserController::class, 'store']);
});

Route::middleware(['auth', 'verified'])->group(function () {
    Route::resource('orders', OrderController::class)->only(['index', 'create', 'store', 'show']);
    Route::post('orders/{order}/pay', [OrderController::class, 'pay'])->name('orders.pay');
});

Route::middleware(['auth', 'role:manager'])->prefix('staff')->name('staff.')->group(function () {
    Route::get('orders', [StaffOrderController::class, 'index'])->name('orders.index');
    Route::patch('orders/{order}/ship', [StaffOrderController::class, 'ship'])->name('orders.ship');
});

Route::prefix('admin')->middleware(['auth', 'admin'])->group(function () {
    Route::get('users', fn () => view('admin.users'));
});
""",
    "app/Http/Controllers/Auth/RegisteredUserController.php": """<?php
class RegisteredUserController extends Controller
{
    public function create() { return view('auth.register'); }

    public function store(Request $request)
    {
        $user = User::create([
            'email' => $request->email,
            'password' => Hash::make($request->password),
        ]);
        Auth::login($user);
        return redirect(route('orders.index'));
    }
}
""",
    "app/Http/Controllers/OrderController.php": """<?php
class OrderController extends Controller
{
    public function index(Request $request)
    {
        $orders = $request->user()->orders()->latest()->get();
        return view('orders.index', compact('orders'));
    }

    public function create() { return view('orders.create'); }

    public function store(Request $request)
    {
        $request->validate(['address' => 'required|min:5']);
        $request->user()->orders()->create([
            'address' => $request->address,
            'status' => OrderStatus::New,
        ]);
        return redirect()->route('orders.index');
    }

    public function show(Order $order)
    {
        abort_if($order->user_id !== auth()->id(), 403);
        return view('orders.show', compact('order'));
    }

    public function pay(Order $order)
    {
        abort_if($order->user_id !== auth()->id(), 403);
        abort_if($order->status !== OrderStatus::New, 400);
        $order->status = OrderStatus::Paid;
        $order->save();
        return back();
    }
}
""",
    "app/Http/Controllers/Staff/StaffOrderController.php": """<?php
class StaffOrderController extends Controller
{
    public function index() { return view('staff.orders', ['orders' => Order::latest()->get()]); }

    public function ship(Order $order)
    {
        abort_unless($order->status === 'paid', 409);
        $order->update(['status' => 'shipped']);
        return back();
    }
}
""",
    "app/Enums/OrderStatus.php": """<?php
enum OrderStatus: string
{
    case New = 'new';
    case Paid = 'paid';
    case Shipped = 'shipped';
}
""",
    "database/migrations/0001_01_01_000000_create_users_table.php": """<?php
return new class extends Migration {
    public function up(): void
    {
        Schema::create('users', function (Blueprint $table) {
            $table->id();
            $table->string('email')->unique();
            $table->enum('role', ['customer', 'manager', 'admin'])->default('customer');
            $table->string('password');
        });
    }
};
""",
    "database/migrations/2024_01_01_000000_create_orders_table.php": """<?php
return new class extends Migration {
    public function up(): void
    {
        Schema::create('orders', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->string('address');
            $table->string('phone')->nullable();
            $table->enum('status', ['new', 'paid', 'shipped'])->default('new');
            $table->timestamps();
        });
    }
};
""",
    "resources/views/layouts/app.blade.php": """<nav>
<a href="{{ route('home') }}">{{ __('Home') }}</a>
<a href="{{ route('orders.index') }}">{{ __('My orders') }}</a>
</nav>
@yield('content')""",
    "resources/views/welcome.blade.php": (
        "@extends('layouts.app')\n@section('content')<h1>Salom</h1>@endsection"
    ),
    "resources/views/auth/register.blade.php": """@extends('layouts.app')
@section('content')
<form method="POST" action="{{ route('register') }}">
    @csrf
    <label for="email">{{ __('Email') }}</label>
    <input id="email" type="email" name="email" required>
    <label for="password">{{ __('Password') }}</label>
    <input id="password" type="password" name="password" required minlength="8">
    <button type="submit">{{ __('Register') }}</button>
</form>
@endsection""",
    "resources/views/orders/index.blade.php": """@extends('layouts.app')
@section('content')
@foreach ($orders as $order)
  <a href="{{ route('orders.show', $order) }}">Ochish</a>
  <form method="POST" action="{{ route('orders.pay', $order) }}">@csrf
    <button type="submit">{{ __('Pay') }}</button>
  </form>
@endforeach
<a href="{{ route('orders.create') }}">{{ __('New order') }}</a>
@endsection""",
    "resources/views/orders/create.blade.php": """@extends('layouts.app')
@section('content')
<form method="POST" action="{{ route('orders.store') }}">@csrf
  <label for="address">Manzil</label><input id="address" name="address" required minlength="5">
  <button type="submit">Buyurtma berish</button>
</form>
@endsection""",
    "resources/views/orders/show.blade.php": (
        "@extends('layouts.app')\n@section('content')<p>Buyurtma</p>@endsection"
    ),
    "resources/views/staff/orders.blade.php": """@extends('layouts.app')
@section('content')
@foreach ($orders as $order)
<form method="POST" action="{{ route('staff.orders.ship', $order) }}">@csrf @method('PATCH')
  <button type="submit">Jo'natish</button>
</form>
@endforeach
@endsection""",
    "resources/views/admin/users.blade.php": "<h1>Users</h1>",
    "lang/uz.json": (
        '{"Home": "Bosh sahifa", "My orders": "Buyurtmalarim", "Email": "Email",'
        ' "Password": "Parol", "Register": "Ro\'yxatdan o\'tish", "Pay": "To\'lash",'
        ' "New order": "Yangi buyurtma"}'
    ),
}


def test_tokenizer_helpers() -> None:
    assert laravel_path("orders/{order}/pay") == "/orders/:order/pay"
    assert laravel_path("posts/{slug?}") == "/posts/:slug"
    assert split_top("a('x;y', [1, 2]); b(function () { c(); })", ";") == [
        "a('x;y', [1, 2])",
        " b(function () { c(); })",
    ]


def test_laravel_routes_middleware_controllers_and_views(
    tmp_path: Path, write_files: Writer
) -> None:
    result = scan(write_files(tmp_path, LARAVEL_PROJECT), "http://127.0.0.1:8000")
    bp = result.blueprint
    kinds = {r.id: r.kind for r in bp.roles}
    pages = {p.path: (p.access, p.roles) for p in bp.pages if p.kind == "page"}
    excluded = {p.path for p in bp.excluded}

    assert "laravel" in result.stacks
    assert kinds == {"guest": "guest", "customer": "role", "manager": "role", "admin": "excluded"}
    assert bp.role("customer").self_signup  # type: ignore[union-attr]
    assert pages["/"][0] == "guest" and pages["/register"][0] == "guest"
    both = ("roles", ["customer", "manager"])
    assert pages["/orders"] == both and pages["/orders/create"] == both
    assert pages["/orders/:order"] == both
    assert pages["/staff/orders"] == ("roles", ["manager"])
    assert "/admin/users" in excluded

    order = bp.entity("order")
    assert order is not None and order.owner_field == "user_id" and "phone" in order.pii_fields
    reach = {s.value: s.reachable_by for s in order.statuses}
    assert reach == {
        "new": ["customer", "manager"],
        "paid": ["customer", "manager"],
        "shipped": ["manager"],
    }
    flows = {f.id: f for f in bp.flows}
    labels = [
        s.target.label for s in flows["customer.register"].steps if s.target and s.target.label
    ]
    assert labels == ["Email", "Parol"]
    assert flows["customer.order.create"].steps[0].path == "/orders/create"
    assert flows["customer.order.pay"].needs_status == ["new"]
    ship = flows["manager.order.ship"]
    assert ship.needs_status == ["paid"] and ship.sets_status == "shipped"
    assert ship.steps[-1].target is not None and ship.steps[-1].target.name == "Jo'natish"
    nav = {n["path"]: n["label"] for n in bp.nav}
    assert nav["/orders"] == "Buyurtmalarim"
