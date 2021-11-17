from django.urls import path, re_path
from django.shortcuts import HttpResponse, redirect, render
from types import FunctionType
from django.urls import reverse
from django.utils.safestring import mark_safe
from stark.utils.pagination import Pagination
from django.http import QueryDict
import functools
from django import forms
from web import models
from django.db.models import Q  # 实现数据的复杂操作
from django.db.models import ForeignKey, ManyToManyField


def get_choice_text(title, field):
    """
    对于stark组件中定义列时choice如果想要显示中文信息，调用此方法即可
    :param title:希望页面显示的表头
    :param field:字段名称
    :return:
    """

    def inner(self, obj=None, is_header=None):
        if is_header:
            return title
        method = f"get_{field}_display"
        return getattr(obj, method)()

    return inner


class SearchGroupRow(object):
    def __init__(self, title, queryset_or_tuple, option, query_dict):
        """

        :param title: 组合显示的名称（性别 部门）
        :param queryset_or_tuple: 根据选择的列 传入的queryset对象或元组，
        :param option: 配置
        :param query_dict: request.GET
        """
        # 封装的是一个对象
        self.queryset_or_tuple = queryset_or_tuple
        self.option = option
        self.title = title
        self.query_dict = query_dict

        # 迭代器对象

    def __iter__(self):
        yield '<div class="whole">'
        yield self.title
        yield '</div>'

        yield '<div class="others">'
        total_query_dict = self.query_dict.copy()
        total_query_dict._mutable = True

        origin_value_list = self.query_dict.getlist(self.option.filed)  # 获取值的列表
        if not origin_value_list:
            yield f"<a class='active' href='?{total_query_dict.urlencode()}'>全部</a>"
        else:
            total_query_dict.pop(self.option.filed)
            yield f"<a href='?{total_query_dict.urlencode()}'>全部</a>"
        for item in self.queryset_or_tuple:
            text = self.option.get_text(item)
            # 需要request.GET
            # self.query_dict
            # 获取组合搜索文本背后对应的id
            value = str(self.option.get_value(item))  # 获取值
            query_dict = self.query_dict.copy()  # copy 一份
            query_dict._mutable = True

            origin_value_list = query_dict.getlist(self.option.filed)  # 获取值的列表
            if not self.option.is_multi:
                query_dict[self.option.filed] = value  # 一个字典格式
                if value in origin_value_list:
                    query_dict.pop(self.option.filed)  # 删掉选中的值
                    yield f"<a class='active' href='?{query_dict.urlencode()}'>{text}</a>"
                else:
                    yield f"<a href='?{query_dict.urlencode()}'>{text}</a>"
                print(value, text, self.query_dict)  # urlencode()可以将字典转换成a=1的格式
            else:
                multi_value_list = query_dict.getlist(self.option.filed)
                if value in multi_value_list:
                    multi_value_list.remove(value)
                    query_dict.setlist(self.option.filed,multi_value_list)
                    yield f"<a class='active' href='?{query_dict.urlencode()}'>{text}</a>"
                else:
                    multi_value_list.append(value)
                    query_dict.setlist(self.option.filed,multi_value_list)
                    yield f"<a href='?{query_dict.urlencode()}'>{text}</a>"



        yield '</div>'


class Option(object):
    # 组合搜索(封装数据)
    def __init__(self, filed,is_multi=False, db_condition=None, text_func=None, value_func=None):
        """

        :param filed: 组合搜索关联的字段
        :param db_condition:数据库关联查询时的条件
        :param text_func:此函数用于显示组合按钮页面文本
         :param is_multi=False, 不支持多选 is_multi=True :支持多选
        """
        self.filed = filed
        if not db_condition:
            db_condition = {}
        self.db_condition = db_condition
        self.text_func = text_func
        self.is_choice = False
        self.value_func = value_func
        self.is_multi = is_multi
    def get_value(self, field_object):
        if self.value_func:
            return self.value_func(field_object)
        if self.is_choice:
            return field_object[0]
        return str(field_object.pk)

    def get_db_condition(self, request, *args, **kwargs):
        return self.db_condition

    def get_queryset_or_tuple(self, model_class, request, *args, **kwargs):
        """
        根据字段去获取数据库关联的数据
        :return:
        """
        # 根据gender字符串，去自己对应的model类中找到字段对象，
        field_object = model_class._meta.get_field(self.filed)
        title = field_object.verbose_name
        # 再根据对象去获取相关联数据
        print(self.filed, field_object)
        # 判断field_object是不是ForeignKey类型 or ManyToManyField类型
        if isinstance(field_object, ForeignKey) or isinstance(field_object, ManyToManyField):
            db_condition = self.get_db_condition(request, *args, **kwargs)
            # 返回的是queryset类型
            return SearchGroupRow(title, field_object.remote_field.model.objects.filter(
                **db_condition), self, request.GET)  # ForeignKey.remote_field.model.objects.all()获取ForeignKey中的字段
        else:
            # 返回元组类型
            self.is_choice = True
            return SearchGroupRow(title, field_object.choices, self, request.GET)

    def get_text(self, field_object):
        if self.text_func:
            return self.text_func(field_object)
        if self.is_choice:
            return field_object[1]
        return str(field_object)


class BootStrapModelForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(BootStrapModelForm, self).__init__(*args, **kwargs)
        # 统一给ModelForm生成字段添加样式
        for name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


class StarkHandler(object):
    search_group = []

    def get_search_group(self):
        """
        创建组合搜索功能的钩子
        :return:
        """
        return self.search_group

    def get_search_group_condition(self, request):
        """

        :param request:
        :return:
        """
        condition = {}
        for option in self.get_search_group():
            if option.is_multi:  # 如果多选则走这里，如果单选走下面
                value_list = request.GET.getlist(option.filed)
                if not value_list:
                    continue
                condition[f'{option.filed}__in'] = value_list
            else:
                value = request.GET.getlist(option.filed)
                if not value:
                    continue
                condition[f'{option.filed}__in'] = value

        return condition

    def display_checkbox(self, obj=None, is_header=None):
        if is_header:
            return '选择'
        return mark_safe(f'<input type="checkbox" name="pk" value="{obj.pk}"/>')

    action_list = []

    def action_multi_delete(self, request, *args, **kwargs):
        # 如果想要定制执行成功后的返回值，那么就为action函数设置返回值即可。
        pk_list = request.POST.getlist('pk')
        self.model_class.objects.filter(id__in=pk_list).delete()

    action_multi_delete.text = '批量删除'

    def get_action_dict(self):
        action_dict = {item.__name__: item.text for item in self.action_list}
        return action_dict

    def display_edit(self, obj=None, is_header=None):
        if is_header:
            return "编辑"
        change_url = self.revers_change_url(pk=obj.pk)
        return mark_safe(f'<a href="{change_url}">编辑</a>')

    def display_del(self, obj=None, is_header=None):
        """
        生成带有参数的删除页面
        :param obj:
        :param is_header:
        :return:
        """
        if is_header:
            return "删除"
        change_url = self.revers_del_url(pk=obj.pk)
        return mark_safe(f'<a href="{change_url}">删除</a>')

    def save(self, form, is_update=False):
        """
        默认数据添加时保存，自定义保存数据接口
        :param form:
        :param is_update:
        :return:
        """
        form.save()

    has_add_btn = True

    def get_add_btn(self):
        """
        添加按钮路径
        :return:
        """
        if self.has_add_btn:
            return f"<a class=' btn form-group btn-primary' href='{self.revers_add_url()}'>添加</a>"
        return None

    def revers_add_url(self):
        """
        反向生产带参数的url(跳转到添加页面)
        :return:
        """
        # 根据别名，反向生成url
        name = f"{self.site.namespace}:{self.get_add_urls_name}"
        add_url = reverse(name)
        if not self.request.GET:
            add_url = add_url
        else:
            param = self.request.GET.urlencode()
            new_query_dict = QueryDict(mutable=True)
            new_query_dict['_filter'] = param
            add_url = f"{add_url}?{new_query_dict.urlencode()}"
        return add_url

    def revers_change_url(self, *args, **kwargs):
        """
        反向生产带参数的url(跳转到编辑页面)
        :return:
        """
        # 根据别名，反向生成url
        name = f"{self.site.namespace}:{self.get_change_urls_name}"
        base_url = reverse(name, args=args, kwargs=kwargs)
        if not self.request.GET:
            add_url = base_url
        else:
            param = self.request.GET.urlencode()
            new_query_dict = QueryDict(mutable=True)
            new_query_dict['_filter'] = param
            add_url = f"{base_url}?{new_query_dict.urlencode()}"
        return add_url

    def revers_del_url(self, *args, **kwargs):
        """
        反向生产带参数的url(跳转到删除页面)
        :return:
        """
        # 根据别名，反向生成url
        name = f"{self.site.namespace}:{self.get_delete_urls_name}"
        base_url = reverse(name, args=args, kwargs=kwargs)
        if not self.request.GET:
            add_url = base_url
        else:
            param = self.request.GET.urlencode()
            new_query_dict = QueryDict(mutable=True)
            new_query_dict['_filter'] = param
            add_url = f"{base_url}?{new_query_dict.urlencode()}"
        return add_url

    list_display = []

    def get_list_display(self):
        """
        获取页面上应该显示的列
        :return:
        """
        per_page = 10  # 默认显示10
        value = []
        value.extend(self.list_display)
        return value

    per_page = 2

    def __init__(self, site, model_class, prev):
        self.site = site
        self.model_class = model_class
        self.prev = prev
        self.per_page = self.per_page
        self.request = None

    def revers_list_url(self):
        """
        # 返回参数的url
        :return:
        """
        name = f'{self.site.namespace}:{self.get_list_urls_name}'
        base_url = reverse(name)
        param = self.request.GET.get('_filter')
        if not param:
            return base_url
        else:
            return f"{base_url}?{param}"

    model_form_class = None

    def get_model_form_class(self):
        """
        获取添加数据的表头【name ,title ,depart】
        :return:
        """
        # 预留一个接口，
        if self.model_form_class:
            return self.model_form_class

        # 默认显示全部数据
        class DynamicModelForm(BootStrapModelForm):
            class Meta:
                model = self.model_class
                fields = "__all__"

        return DynamicModelForm

    order_list = []

    def get_order_list(self):
        """
        设置排序
        :return: 
        """
        return self.order_list or ['-id']

    # 姓名中含有关键字或者邮箱中含有关键字
    search_list = []

    def get_search_list(self):
        return self.search_list

    def changelist(self, request, *args, **kwargs):  # 列表页面

        # ##########获取执行列表 ######

        action_dict = self.get_action_dict()
        # action_dict = {func.__name__: func.text for func in action_list} # {'multi_delete':'批量删除','multi_init':'批量初始化'}
        # print(action_dict)
        if request.method == 'POST':
            action_func_name = request.POST.get('action')
            if action_func_name and action_func_name in action_dict:  # 用户方法存在且再我的列表里

                action_response = getattr(self, action_func_name)(request, *args, **kwargs)
                if action_response:  # 如果func有返回值，则执行func,可以跳转到其他页面
                    return action_response

        # # 获取搜索内容
        # search_list = self.get_search_list()
        # # 获取用户搜索框输入内容
        #
        # search_value = request.GET.get('q', None)
        # # 1.如果search_list 中没有值，则不显示搜索框
        # # 2.获取用户提交的关键字
        # # 3.构造条件search__list =
        #
        # conn = Q()
        # conn.connector = 'OR'
        # if search_value:
        #     for item in search_list:
        #         conn.children.append((item, search_value))
        search_list = self.get_search_list()
        search_value = request.GET.get('q', '')
        conn = Q()
        conn.connector = 'OR'
        if search_value:
            for item in search_list:
                conn.children.append((item, search_value))
        print(search_value)

        # ######### 获取 排序########
        order_list = self.get_order_list()
        # 获取组合搜索
        search_group_condition = self.get_search_group_condition(request)
        # ####### 分页处理 ###################
        queryset = self.model_class.objects.filter(conn).filter(**search_group_condition).order_by(*order_list)
        query_params = request.GET.copy()
        query_params._mutable = True
        # query_params['page'] = 2
        # 从数据库中获取所有数据
        # 根据url获取的 page = 3
        pager = Pagination(current_page=request.GET.get('page'),
                           all_count=queryset.count(),
                           base_url=request.path_info,
                           query_params=query_params,
                           per_page=self.per_page,
                           )
        data_list = queryset[pager.start:pager.end]
        # http://127.0.0.1:8000/stark/app01/userinfo/list/ == app01.models.Depart
        # 页面要显示的列
        list_display = self.get_list_display()
        # 构造表头
        header_list = []
        for key in list_display:
            if isinstance(key, FunctionType):  # 判断key是否是一个函数  from types import FunctionType
                verbose_name = key(self, obj=None, is_header=True)
            else:
                verbose_name = self.model_class._meta.get_field(key).verbose_name
                print(verbose_name)
            header_list.append(verbose_name)
        # 处理表的内容
        # data_list = self.model_class.objects.all()  # 获取表的所有数据

        # ########添加按钮########
        add_btn = self.get_add_btn()
        body_list = []
        for row in data_list:
            tr_list = []
            for key in list_display:
                if isinstance(key, FunctionType):  # 判断key是否是一个函数  from types import FunctionType
                    tr_list.append(key(self, obj=row, is_header=False))
                else:
                    tr_list.append(getattr(row, key))
            body_list.append(tr_list)

        # #########组合搜索###############
        search_group_list = []
        search_group = self.search_group

        for option_object in search_group:  # gender and depart
            row = option_object.get_queryset_or_tuple(self.model_class, request, *args, **kwargs)
            search_group_list.append(row)
        return render(request, 'stark/changelist.html', {'data_list': data_list,
                                                         "header_list": header_list,
                                                         "body_list": body_list,
                                                         "pager": pager,
                                                         "add_btn": add_btn,
                                                         "search_list": search_list,
                                                         "search_value": search_value,
                                                         "action_dict": action_dict,
                                                         'search_group_row_list': search_group_list},
                      )

    def add_view(self, request, *args, **kwargs):  # 添加页面
        """
        添加页面
        :param request:
        :return:
        """

        model_form_class = self.get_model_form_class()
        if request.method == 'GET':
            form = model_form_class()
            print(request.method, "request.method")
            return render(request, 'stark/change.html', {'form': form})
        form = model_form_class(data=request.POST)
        if form.is_valid():
            self.save(form, is_update=False)
            # 在数据库保存成功后，跳转会列表页面（携带原来的参数）
            return redirect(self.revers_list_url())
        return render(request, 'stark/change.html', {'form': form})

    def delete_view(self, request, pk, *args, **kwargs):  # 删除页面
        origin_list_url = self.revers_list_url()  # 获取反向生成带数据的列表页面地址
        if request.method == 'GET':
            return render(request, 'stark/delete.html', {'cancel': origin_list_url})
        self.model_class.objects.filter(pk=pk).delete()
        return redirect(origin_list_url)

    def change_view(self, request, pk, *args, **kwargs):  # 修改页面
        current_obj = self.model_class.objects.filter(pk=pk).first()
        if not current_obj:
            return HttpResponse('要修改的数据不存在')
        model_form_class = self.get_model_form_class()
        if request.method == 'GET':
            form = model_form_class(instance=current_obj)
            return render(request, 'stark/change.html', {'form': form})
        form = model_form_class(data=request.POST, instance=current_obj)
        if form.is_valid():
            self.save(form, is_update=False)
            # 在数据库保存成功后，跳转会列表页面（携带原来的参数）
            return redirect(self.revers_list_url())
        return render(request, 'stark/change.html', {'form': form})

    def get_url_name(self, param):
        app_label, model_name = self.model_class._meta.app_label, self.model_class._meta.model_name
        if self.prev:
            return f'{app_label}_{model_name}_{self.prev}_{param}'
        else:
            return f'{app_label}_{model_name}_{param}'

    @property
    def get_add_urls_name(self):
        """
        获取添加页面url的name
        :return:
        """
        return self.get_url_name('add')

    @property
    def get_list_urls_name(self):
        """
               获取列表页面url的name
               :return:
               """
        return self.get_url_name('list')

    @property
    def get_change_urls_name(self):
        """
               获取编辑页面url的name
               :return:
               """
        return self.get_url_name('change')

    @property
    def get_delete_urls_name(self):
        """
               获取删除页面url的name
               :return:
               """
        return self.get_url_name('delete')

    def wapper(self, func):
        @functools.wraps(func)
        def inner(request, *args, **kwargs):
            self.request = request
            return func(request, *args, **kwargs)

        return inner

    def get_urls(self):
        patterns = [

            re_path(r'list/$', self.wapper(self.changelist), name=self.get_list_urls_name),
            re_path(r'add/$', self.wapper(self.add_view), name=self.get_add_urls_name),
            re_path(r'change/(?P<pk>\d+)/$', self.wapper(self.change_view), name=self.get_change_urls_name),
            re_path(r'delete/(?P<pk>\d+)/$', self.wapper(self.delete_view), name=self.get_delete_urls_name),
        ]
        patterns.extend(self.extra_urls())
        return patterns

    def extra_urls(self):
        return []


class StarkSite(object):
    def __init__(self):
        self._registry = []
        self.app_name = 'stark'
        self.namespace = 'stark'

    def register(self, model_class, handler_class=None, prev=None):
        """
        :param prev: 生成url  的前缀
        :param model_class: 是models中的数据库相关类 相当于执行models.UserInfo/Depart/等数据库中的类
        :param handler_class:处理请求的视图函数所在的类
        :return:
        """
        if not handler_class:
            handler_class = StarkHandler
        self._registry.append(
            {'model_class': model_class, 'handler': handler_class(self, model_class, prev), "prev": prev})
        """
         [
         {"models":models.Depart,'handler': handler_class(models.Depart)}
         {"models":models.UserInfo,'handler': handler_class(models.UserInfo)}
         {"models":models.Host,'handler': handler_class(models.Host)}
         ]
          """

    def get_urls(self):
        patterns = []
        for item in self._registry:
            model_class = item['model_class']
            handler = item['handler']
            prev = item['prev']
            app_label, model_name = model_class._meta.app_label, model_class._meta.model_name
            if prev:
                # patterns.append(re_path(r'%s/%s/%s/list/$' % (app_label, model_name, prev), handler.changelist))
                # patterns.append(re_path(r'%s/%s/%s/add/$' % (app_label, model_name, prev), handler.add_view))
                # patterns.append(
                #     re_path(r'%s/%s/%s/change/(\d+)/$' % (app_label, model_name, prev), handler.change_view))
                # patterns.append(
                #     re_path(r'%s/%s/%s/delete/(\d+)/$' % (app_label, model_name, prev), handler.delete_view))
                patterns.append(re_path(r'%s/%s/%s/' % (app_label, model_name, prev),
                                        (handler.get_urls(), None, None)))

            else:
                # patterns.append(re_path(r'%s/%s/list/$' % (app_label, model_name,), handler.changelist))
                # patterns.append(re_path(r'%s/%s/add/$' % (app_label, model_name,), handler.add_view))
                # patterns.append(re_path(r'%s/%s/change/(\d+)/$' % (app_label, model_name,), handler.change_view))
                # patterns.append(re_path(r'%s/%s/delete/(\d+)/$' % (app_label, model_name,), handler.delete_view))
                patterns.append(
                    re_path(r'%s/%s/' % (app_label, model_name,), (handler.get_urls(), None, None)))

        return patterns

    @property
    def urls(self):
        # print(self.get_urls())
        return self.get_urls(), self.app_name, self.namespace


site = StarkSite()
