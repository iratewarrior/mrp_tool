import pandas as pd
import streamlit as st
import base64

page_bg_img = f"""
<style>
[data-testid="stAppViewContainer"] > .main {{
background-image: url("https://images.unsplash.com/photo-1637825891028-564f672aa42c?q=80&w=1740&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D");
background-size: 180%;
background-position: top left;
background-repeat: no-repeat;
background-attachment: local;
}}

[data-testid="stHeader"] {{
background: rgba(0,0,0,0);
}}

[data-testid="stToolbar"] {{
right: 2rem;
}}
</style>
"""



# Функция для нахождения всех аналогов для конкретного кода
def find_analogs(er_code, df_analogs):
    analogs = df_analogs[(df_analogs['Материал.Код'] == er_code) | 
                         (df_analogs['Аналог.Код'] == er_code)]
    all_codes = set(analogs['Материал.Код'].tolist() + analogs['Аналог.Код'].tolist())
    all_codes.discard(er_code)
    return list(all_codes)

# Функция для подсчета суммарного остатка по каждому коду и его аналогам
def calculate_aggregated_stock(df_specs, df_analogs, df_stocks, excluded_codes=[]):
    aggregated_stocks = {}
    for code in df_specs['Код']:
        if code not in excluded_codes:
            all_codes = [code] + find_analogs(code, df_analogs)
            total_stock = df_stocks[df_stocks['Код'].isin(all_codes)]['В наличии'].sum()
            aggregated_stocks[code] = total_stock
        else:
            aggregated_stocks[code] = 0  # Установить 0 для исключенных компонентов
    return aggregated_stocks

# Функция для расчета минимального количества продукта, которое можно собрать
def calculate_production_capacity(df_specs, df_analogs, df_stocks, aggregated_stocks, excluded_codes=[]):
    capacity = {}
    for product in df_specs['Продукт'].unique():
        product_specs = df_specs[df_specs['Продукт'] == product]
        min_capacity = float('inf')
        for _, row in product_specs.iterrows():
            if row['Код'] not in excluded_codes:
                analogs = find_analogs(row['Код'], df_analogs)
                total_stock = df_stocks[df_stocks['Код'].isin([row['Код']] + analogs)]['В наличии'].sum()
                current_capacity = total_stock // row['Количество на изделие']
                if current_capacity < min_capacity:
                    min_capacity = current_capacity
        capacity[product] = min_capacity if min_capacity != float('inf') else 0
    return capacity

# Функция для расчета необходимых к дозакупке компонентов
def calculate_additional_requirements(df_specs, df_stocks, df_analogs, df_overuse, target_qty, aggregated_stocks):
    requirements = {}
    for product, qty in target_qty.items():
        if qty == 0:
            continue
        product_specs = df_specs[df_specs['Продукт'] == product]
        for _, row in product_specs.iterrows():
            needed = qty * row['Количество на изделие']
            excess_rate = df_overuse.loc[df_overuse['Код'] == row['Код'], 'Коэффициент брака производство']
            needed *= (1 + excess_rate.iloc[0] if not excess_rate.empty else 1)
            available = aggregated_stocks.get(row['Код'], 0)
            additional_required = needed - available
            if additional_required > 0:
                if row['Код'] in requirements:
                    requirements[row['Код']]['Дополнительно'] += additional_required
                else:
                    requirements[row['Код']] = {
                        'Описание': row['Описание'],
                        'Дополнительно': additional_required
                    }
    
    if requirements:
        requirements_df = pd.DataFrame.from_dict(requirements, orient='index').reset_index().rename(columns={'index': 'Код'})
        requirements_df['Дополнительно'] = requirements_df['Дополнительно'].fillna(0).astype(float).round(0).astype(int)
        return requirements_df
    else:
        return pd.DataFrame(columns=['Код', 'Описание', 'Дополнительно'])

# Загрузка данных
df_specs = pd.read_excel('00_спецификации.xlsx')
df_analogs = pd.read_excel('01_аналоги.xlsx').drop_duplicates()
df_stocks = pd.read_excel('02_остатки_ERP.xlsx')
df_overuse = pd.read_excel('03_перерасход.xlsx')

# Интерфейс пользователя в Streamlit
st.set_page_config(page_title="Планирование материальных потребностей", layout="wide")
st.title('Планирование материальных потребностей (MRP)')

st.sidebar.warning('Данный инструмент призван помогать в оценивании теущих возможностей производства, учитывая текущие остатки компонентов на складах, а также в планировании дозакупки необходимых комопнентов.')

# Боковая панель для ввода данных
st.sidebar.title('Настройки')

# Выбор продукта из выпадающего списка
selected_product_for_target_qty = st.sidebar.selectbox('Выберите продукт для ввода целевого количества', df_specs['Продукт'].unique())
target_qty = {selected_product_for_target_qty: st.sidebar.number_input(f'Целевое количество {selected_product_for_target_qty}', min_value=0, key=selected_product_for_target_qty)}

# Мультивыбор для исключения компонентов
excluded_codes = st.sidebar.multiselect('Выберите компоненты для исключения', df_specs['Код'].unique(), key='excluded_codes')

st.sidebar.link_button("Инструкция к инструменту", "https://drive.yadro.com/s/pSwYm4zifsqQeW9")

# Агрегация остатков комплектующих с учетом аналогов
aggregated_stocks = calculate_aggregated_stock(df_specs, df_analogs, df_stocks, excluded_codes)
df_specs['Агрегированные остатки'] = df_specs['Код'].map(aggregated_stocks).round(0).astype(int)
df_specs['Входимость в 1 изделие'] = df_specs['Количество на изделие']
df_specs['Комплектов'] = (df_specs['Агрегированные остатки'] // df_specs['Количество на изделие']).round(0).astype(int)

# Фильтр для отображения агрегированных остатков от меньшего к большему
df_specs_sorted = df_specs.sort_values(by='Агрегированные остатки')

# Расчет минимальной возможности производства на основе текущих остатков
production_capacity = calculate_production_capacity(df_specs, df_analogs, df_stocks, aggregated_stocks, excluded_codes)

# Минимальное количество каждого продукта, которое можно собрать
st.subheader('Минимальное количество каждого продукта, которое можно собрать:')
styled_capacity_df = pd.DataFrame.from_dict(production_capacity, orient='index', columns=['Минимальное количество']).round(0).astype(int)
st.dataframe(styled_capacity_df.applymap(lambda x: '{:,.0f}'.format(x).replace(',', ' ')), use_container_width=True)

st.subheader(f'Агрегированные остатки для {selected_product_for_target_qty}')

# Применение выбор продукта для отображения агрегированных остатков из боковой панели
selected_product = selected_product_for_target_qty
df_selected_product = df_specs[df_specs['Продукт'] == selected_product]

# Применение форматирования только к числовым столбцам
numeric_columns = ['Агрегированные остатки', 'Комплектов']
df_selected_product[numeric_columns] = df_selected_product[numeric_columns].applymap(lambda x: '{:,.0f}'.format(x).replace(',', ' '))
df_selected_product['Входимость в 1 изделие'] = df_selected_product['Входимость в 1 изделие'].apply(lambda x: '{:,.3f}'.format(x))

# Отображение таблицы с агрегированными остатками
st.dataframe(df_selected_product[['Код', 'Описание', 'Агрегированные остатки', 'Входимость в 1 изделие', 'Комплектов']], use_container_width=True)

# Проверка наличия целевых количеств перед расчетом дополнительных требований
if any(target_qty.values()):
    # Расчет необходимых к дозакупке компонентов
    additional_requirements_df = calculate_additional_requirements(df_specs, df_stocks, df_analogs, df_overuse, target_qty, aggregated_stocks)
    
    st.subheader('Необходимость в дозакупке компонентов для плана производства:')
    additional_requirements_df = additional_requirements_df[additional_requirements_df['Дополнительно'] > 0].fillna(0).astype({'Дополнительно': 'int'})
    additional_requirements_df['Дополнительно'] = additional_requirements_df['Дополнительно'].apply(lambda x: '{:,.0f}'.format(x).replace(',', ' '))
    st.dataframe(additional_requirements_df[['Код', 'Описание', 'Дополнительно']], use_container_width=True)
