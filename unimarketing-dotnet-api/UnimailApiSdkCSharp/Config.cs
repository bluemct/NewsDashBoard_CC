namespace Unimarketing.UnimailApiSdk.CSharp
{
    public class Config
    {
        public static string APIURL = "http://services.unimarketing.org/";
        //public static string APIURL = "http://xp.unimail.co/uniapi/services/";
        //public static string APIURL = "http://192.168.0.178:8080/uniapi/services/";

        public static AuthModeEnum AUTHMODE = AuthModeEnum.APIKEY;

        //public static string APIKEY = "www.huuug.com";
        //public static string APISECRET = "JwXlEGkvRuoKCu41ZUb7hh53xNU=";


        public static string APIKEY = "daemon";
        public static string APISECRET = "{SHA}4V+XZ+5gQiTIDBANhmJSzyFeWPM=";
        

        public static string UM_ACCOUNT = "account/";  //账户信息
        public static string UM_LIST = "list/"; //列表
        public static string UM_CONTACT = "contact/";//联系人
        public static string UM_CONTACT_IMPORT = "contactimport/"; //联系人导入
        public static string UM_MESSAGE = "message/"; //邮件
        public static string UM_SCHEDULE = "schedule/";
        public static string UM_REPORT = "report/"; //报表
        public static string UM_REPORT_EVENT_OPEN_DETAIL = "report/event/open/detail"; // 邮件打开明细报表
        public static string UM_EVENT_OPEN = "event/open"; //邮件打开信息
        public static string UM_REPORT_EVENT_CLICK_DETAIL = "report/event/click/detail"; //邮件点击明细报表
        public static string UM_EVENT_CLICK = "event/click"; // 邮件点击详细信息
        public static string UM_REPORT_EVENT_DELIVERY_DETAIL = "report/event/delivery/detail"; // 邮件发送明细报表
        public static string UM_EVENT_DELIVERY = "event/delivery"; //邮件发送信息
        public static string UM_SENDTASK = "schedule"; //发送计划
        public static string UM_LINK = "link/";
        public static string UM_FOLDER = "folder/";

        public static string UM_MESSAGE_SEND = "message/send";
    }
}
