import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Orders Dashboard | لوحة تحليل الطلبات",
    page_icon="🍽️",
    layout="wide"
)

st.markdown("""
<style>
    .stApp { direction: rtl; }
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        border-right: 4px solid #2196F3;
    }
    .warning-box {
        background: #fff3cd;
        border: 1px solid #ffc107;
        border-radius: 8px;
        padding: 10px;
        margin: 5px 0;
    }
    .danger-box {
        background: #f8d7da;
        border: 1px solid #dc3545;
        border-radius: 8px;
        padding: 10px;
        margin: 5px 0;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# LOAD & MERGE DATA
# ─────────────────────────────────────────────────────────────
@st.cache_data
def load_data(order_file, payment_file, items_file):
    order_df   = pd.read_csv(order_file)
    payment_df = pd.read_csv(payment_file)
    items_df   = pd.read_csv(items_file)

    # ── Fix business_date using created_at rule ───────────────
    order_df['created_at'] = pd.to_datetime(order_df['created_at'], errors='coerce')

    def adjust_date(row):
        try:
            t = row['created_at'].time()
            # 12:00 AM → 05:00 AM  =  previous business day
            if time(0, 0) <= t < time(5, 0):
                return (row['created_at'] - timedelta(days=1)).date()
            return row['created_at'].date()
        except Exception:
            return pd.to_datetime(row['business_date'], errors='coerce').date()

    order_df['business_date_adj'] = order_df.apply(adjust_date, axis=1)
    order_df['business_date_adj'] = pd.to_datetime(order_df['business_date_adj'])

    # ── Payment: sum per order (handles split payments) ───────
    payment_agg = (
        payment_df
        .groupby('order_reference')
        .agg(
            payment_method_name=('payment_method_name', lambda x: ' + '.join(x.unique())),
            amount_paid=('amount', 'sum')
        )
        .reset_index()
    )

    # ── Merge Order + Payment ─────────────────────────────────
    merged = order_df.merge(
        payment_agg,
        left_on='reference',
        right_on='order_reference',
        how='left'
    )

    merged['payment_diff']     = (merged['total_price'] - merged['amount_paid']).round(2)
    merged['has_payment_diff'] = merged['payment_diff'].abs() > 0.01

    # ── Items: keep only Products (not modifiers) for display ─
    # But include all for order_status check
    items_status = items_df[['order_reference','order_status']].drop_duplicates(subset='order_reference')

    # Products only for item list
    products = (
        items_df[items_df['type'] == 'Product']
        [['order_reference', 'order_status', 'type', 'name', 'quantity', 'total_price']]
    )

    # ── Orders with non-Done status (from items sheet) ────────
    non_done = items_df[items_df['order_status'].str.lower() != 'done'][['order_reference','order_status']].drop_duplicates()

    return merged, products, items_df, non_done, payment_df

# ─────────────────────────────────────────────────────────────
# SIDEBAR – File Upload
# ─────────────────────────────────────────────────────────────
st.sidebar.header("📂 رفع الملفات")
order_file   = st.sidebar.file_uploader("ملف الطلبات (Order.csv)",   type="csv")
payment_file = st.sidebar.file_uploader("ملف الدفع (Order_Payment.csv)", type="csv")
items_file   = st.sidebar.file_uploader("ملف المنتجات (Order_Items.csv)", type="csv")

if not (order_file and payment_file and items_file):
    st.title("🍽️ لوحة تحليل الطلبات")
    st.info("يرجى رفع الملفات الثلاثة من الشريط الجانبي للبدء")
    st.stop()

df, products, items_df, non_done, payment_df = load_data(order_file, payment_file, items_file)

# ─────────────────────────────────────────────────────────────
# SIDEBAR – Filters
# ─────────────────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.header("🔍 الفلاتر")

branches = ["الكل"] + sorted(df['branch_name'].dropna().unique().tolist())
sel_branch = st.sidebar.selectbox("الفرع", branches)

sources = ["الكل"] + sorted(df['source'].dropna().unique().tolist())
sel_source = st.sidebar.selectbox("مصدر الطلب", sources)

types = ["الكل"] + sorted(df['type'].dropna().unique().tolist())
sel_type = st.sidebar.selectbox("نوع الطلب", types)

min_date = df['business_date_adj'].min().date()
max_date = df['business_date_adj'].max().date()
date_range = st.sidebar.date_input("نطاق التاريخ", value=(min_date, max_date), min_value=min_date, max_value=max_date)

# Apply filters
filt = df.copy()
if sel_branch != "الكل":
    filt = filt[filt['branch_name'] == sel_branch]
if sel_source != "الكل":
    filt = filt[filt['source'] == sel_source]
if sel_type != "الكل":
    filt = filt[filt['type'] == sel_type]
if len(date_range) == 2:
    filt = filt[
        (filt['business_date_adj'].dt.date >= date_range[0]) &
        (filt['business_date_adj'].dt.date <= date_range[1])
    ]

# ─────────────────────────────────────────────────────────────
# MAIN CONTENT
# ─────────────────────────────────────────────────────────────
st.title("🍽️ لوحة تحليل الطلبات")

# Non-done orders alert (always visible regardless of filters)
if len(non_done) > 0:
    st.markdown(f"""
    <div class="danger-box">
    ⚠️ <b>تنبيه:</b> يوجد {len(non_done)} طلب بحالة غير (Done) في شيت المنتجات
    </div>
    """, unsafe_allow_html=True)

# ── KPI Row ──────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("📦 إجمالي الطلبات",   f"{len(filt):,}")
k2.metric("💰 المبيعات (شامل ضريبة)",  f"{filt['total_price'].sum():,.1f} ر.س")
k3.metric("💵 المبيعات (قبل ضريبة)",   f"{filt['subtotal'].sum():,.1f} ر.س")
k4.metric("🏷️ إجمالي الخصومات",        f"{filt['discounts'].sum():,.1f} ر.س")
k5.metric("⚠️ طلبات بفروقات دفع",      f"{filt['has_payment_diff'].sum():,}")

st.markdown("---")

# ── Tabs ─────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📋 تفاصيل الطلبات",
    "📊 تحليل المبيعات",
    "💳 قنوات الدفع",
    "🛍️ المنتجات",
    "⚠️ فروقات الدفع"
])

# ─────────────────────────────────────────────────────────────
# TAB 1 – Order Details
# ─────────────────────────────────────────────────────────────
with tab1:
    st.subheader("📋 تفاصيل الطلبات")

    # Merge items (products only) for display
    filt_products = products[products['order_reference'].isin(filt['reference'])]
    items_grouped = (
        filt_products
        .groupby('order_reference')
        .apply(lambda x: ' | '.join(x['name'].astype(str) + ' ×' + x['quantity'].astype(str)))
        .reset_index()
        .rename(columns={0: 'المنتجات'})
    )
    # Get order_status per order
    items_status = (
        items_df[items_df['order_reference'].isin(filt['reference'])]
        [['order_reference','order_status']]
        .drop_duplicates(subset='order_reference')
    )

    display = filt[[
        'reference','business_date_adj','branch_name','type','source',
        'customer_name','subtotal','total_price','discount_name','discounts',
        'payment_method_name','amount_paid','has_payment_diff'
    ]].copy()

    display = display.merge(items_grouped, left_on='reference', right_on='order_reference', how='left').drop(columns=['order_reference'], errors='ignore')
    display = display.merge(items_status,  left_on='reference', right_on='order_reference', how='left').drop(columns=['order_reference'], errors='ignore')

    display.rename(columns={
        'reference':            'رقم الطلب',
        'business_date_adj':    'تاريخ العمل',
        'branch_name':          'الفرع',
        'type':                 'نوع الطلب',
        'source':               'المصدر',
        'customer_name':        'اسم العميل',
        'subtotal':             'المبلغ قبل الضريبة',
        'total_price':          'المبلغ شامل الضريبة',
        'discount_name':        'اسم الخصم',
        'discounts':            'قيمة الخصم',
        'payment_method_name':  'قناة الدفع',
        'amount_paid':          'المبلغ المدفوع',
        'has_payment_diff':     'فرق في الدفع؟',
        'order_status':         'حالة الطلب',
        'المنتجات':             'المنتجات',
    }, inplace=True)

    display['تاريخ العمل'] = display['تاريخ العمل'].dt.strftime('%Y-%m-%d')
    display['فرق في الدفع؟'] = display['فرق في الدفع؟'].map({True: '⚠️ نعم', False: '✅ لا'})

    col_order = [
        'رقم الطلب','تاريخ العمل','الفرع','نوع الطلب','المصدر','حالة الطلب',
        'اسم العميل','المبلغ قبل الضريبة','المبلغ شامل الضريبة',
        'اسم الخصم','قيمة الخصم','قناة الدفع','المبلغ المدفوع','فرق في الدفع؟','المنتجات'
    ]
    existing_cols = [c for c in col_order if c in display.columns]
    st.dataframe(display[existing_cols], use_container_width=True, height=500)

    # Export
    csv_data = display[existing_cols].to_csv(index=False, encoding='utf-8-sig')
    st.download_button("⬇️ تحميل كـ CSV", csv_data, "orders_detail.csv", "text/csv")

# ─────────────────────────────────────────────────────────────
# TAB 2 – Sales Analysis
# ─────────────────────────────────────────────────────────────
with tab2:
    st.subheader("📊 تحليل المبيعات")

    c1, c2 = st.columns(2)

    # Daily sales
    daily = filt.groupby('business_date_adj').agg(
        orders=('reference','count'),
        revenue=('total_price','sum')
    ).reset_index()
    daily['business_date_adj'] = daily['business_date_adj'].dt.strftime('%Y-%m-%d')

    with c1:
        fig = px.bar(daily, x='business_date_adj', y='revenue',
                     labels={'business_date_adj':'التاريخ','revenue':'الإيراد (ر.س)'},
                     title='الإيراد اليومي', color_discrete_sequence=['#2196F3'])
        fig.update_layout(xaxis_title='التاريخ', yaxis_title='الإيراد')
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig2 = px.line(daily, x='business_date_adj', y='orders',
                       labels={'business_date_adj':'التاريخ','orders':'عدد الطلبات'},
                       title='عدد الطلبات اليومية', markers=True,
                       color_discrete_sequence=['#4CAF50'])
        st.plotly_chart(fig2, use_container_width=True)

    # By branch
    branch_rev = filt.groupby('branch_name').agg(
        orders=('reference','count'),
        revenue=('total_price','sum'),
        discounts=('discounts','sum')
    ).reset_index().sort_values('revenue', ascending=False)

    fig3 = px.bar(branch_rev, x='branch_name', y='revenue', color='branch_name',
                  labels={'branch_name':'الفرع','revenue':'الإيراد'},
                  title='الإيراد حسب الفرع')
    st.plotly_chart(fig3, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        src_count = filt.groupby('source')['reference'].count().reset_index()
        src_count.columns = ['المصدر','عدد الطلبات']
        fig4 = px.pie(src_count, names='المصدر', values='عدد الطلبات', title='توزيع مصادر الطلبات')
        st.plotly_chart(fig4, use_container_width=True)

    with c4:
        type_count = filt.groupby('type')['reference'].count().reset_index()
        type_count.columns = ['نوع الطلب','عدد']
        fig5 = px.pie(type_count, names='نوع الطلب', values='عدد', title='توزيع أنواع الطلبات')
        st.plotly_chart(fig5, use_container_width=True)

# ─────────────────────────────────────────────────────────────
# TAB 3 – Payment Channels
# ─────────────────────────────────────────────────────────────
with tab3:
    st.subheader("💳 تحليل قنوات الدفع")

    # Filter payment by orders in filt
    pay_filt = payment_df[payment_df['order_reference'].isin(filt['reference'])]

    channel_agg = pay_filt.groupby('payment_method_name').agg(
        count=('order_reference','count'),
        total=('amount','sum')
    ).reset_index().sort_values('total', ascending=False)
    channel_agg.columns = ['قناة الدفع','عدد المعاملات','إجمالي المبلغ']

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(channel_agg, x='قناة الدفع', y='إجمالي المبلغ',
                     color='قناة الدفع', title='إجمالي المبيعات حسب قناة الدفع')
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig2 = px.pie(channel_agg, names='قناة الدفع', values='إجمالي المبلغ',
                      title='توزيع قنوات الدفع')
        st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(channel_agg, use_container_width=True)

# ─────────────────────────────────────────────────────────────
# TAB 4 – Products
# ─────────────────────────────────────────────────────────────
with tab4:
    st.subheader("🛍️ تحليل المنتجات")

    prod_filt = products[products['order_reference'].isin(filt['reference'])]

    top_products = (
        prod_filt[prod_filt['type'] == 'Product']
        .groupby('name')
        .agg(qty=('quantity','sum'), revenue=('total_price','sum'))
        .reset_index()
        .sort_values('qty', ascending=False)
        .head(20)
    )
    top_products.columns = ['اسم المنتج','الكمية المباعة','إجمالي الإيراد']

    fig = px.bar(top_products, x='اسم المنتج', y='الكمية المباعة',
                 title='أكثر 20 منتج مبيعاً (حسب الكمية)',
                 color='الكمية المباعة', color_continuous_scale='Blues')
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(top_products, use_container_width=True)

    # Non-done status orders
    if len(non_done) > 0:
        st.markdown("### ⚠️ طلبات بحالة غير (Done)")
        non_done_detail = non_done.merge(
            df[['reference','branch_name','business_date_adj','total_price']],
            left_on='order_reference', right_on='reference', how='left'
        )
        non_done_detail.rename(columns={
            'order_reference':'رقم الطلب',
            'order_status':'الحالة',
            'branch_name':'الفرع',
            'business_date_adj':'التاريخ',
            'total_price':'المبلغ'
        }, inplace=True)
        st.dataframe(non_done_detail[['رقم الطلب','الحالة','الفرع','التاريخ','المبلغ']], use_container_width=True)

# ─────────────────────────────────────────────────────────────
# TAB 5 – Payment Differences
# ─────────────────────────────────────────────────────────────
with tab5:
    st.subheader("⚠️ تقرير فروقات الدفع")

    diff_df = filt[filt['has_payment_diff'] == True][[
        'reference','branch_name','business_date_adj',
        'total_price','amount_paid','payment_diff','payment_method_name'
    ]].copy()

    if len(diff_df) == 0:
        st.success("✅ لا توجد فروقات في الدفع ضمن الفترة المحددة")
    else:
        st.warning(f"⚠️ يوجد {len(diff_df)} طلب بفروقات في الدفع")
        diff_df['business_date_adj'] = diff_df['business_date_adj'].dt.strftime('%Y-%m-%d')
        diff_df.rename(columns={
            'reference':           'رقم الطلب',
            'branch_name':         'الفرع',
            'business_date_adj':   'التاريخ',
            'total_price':         'إجمالي الطلب',
            'amount_paid':         'المبلغ المدفوع',
            'payment_diff':        'الفرق',
            'payment_method_name': 'قناة الدفع'
        }, inplace=True)

        st.dataframe(diff_df, use_container_width=True)

        # ── Info about 0-value orders missing payment ─────────
        zero_orders = df[(df['total_price'] == 0) & (df['amount_paid'].isna())]
        if len(zero_orders) > 0:
            st.info(f"""
            ℹ️ ملاحظة: يوجد {len(zero_orders)} طلب بقيمة صفر (0 ر.س) غير موجودة في شيت الدفع — 
            هذا طبيعي لأن الطلبات الصفرية لا تُسجَّل في المدفوعات.
            """)

    st.markdown("### ℹ️ ملخص المقارنة")
    total_orders   = len(df)
    orders_in_pay  = df['amount_paid'].notna().sum()
    orders_no_pay  = df['amount_paid'].isna().sum()
    split_pay      = payment_df.groupby('order_reference').size()
    split_count    = (split_pay > 1).sum()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("إجمالي الطلبات",          f"{total_orders:,}")
    m2.metric("طلبات موجودة في الدفع",   f"{orders_in_pay:,}")
    m3.metric("طلبات بدون سجل دفع",      f"{orders_no_pay:,}")
    m4.metric("طلبات بدفعات مقسمة",       f"{split_count:,}")
